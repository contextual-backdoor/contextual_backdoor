import os
import re
import sys
import openai
import numpy as np
import math
import random
import time
import json
import argparse

module_path = os.path.abspath(os.path.join('..'))
if module_path not in sys.path:
    sys.path.append(module_path)

from prompts.nlvr_sample_set import *
from prompts.prompt_modifier import *
from transformers import (AutoModelForCausalLM, AutoTokenizer, AutoConfig, top_k_top_p_filtering)
from accelerate import Accelerator, dispatch_model, infer_auto_device_map


def get_model(model_name):
    if "gpt" in model_name or "davinci" in model_name:
        return None, None
    tokenizer = AutoTokenizer.from_pretrained(
        model_name,
        trust_remote_code=True,
        use_fast=False
    )
    if not tokenizer.pad_token:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = 'left'
    model_kwargs = {"low_cpu_mem_usage": True, "use_cache": False}
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.float16,
        trust_remote_code=True,
        **model_kwargs
    ).eval()

    device_map = {}
    model_layers = 32
    if model_name.endswith("65b") or model_name.endswith("65b-hf"):
        model_layers = 80
    elif model_name.endswith("30b") or model_name.endswith("30b-hf"):
        model_layers = 60
    for i in range(model_layers):
        layer = "model.layers." + str(i)
        device_map[layer] = int(i / (model_layers) * 4)
    device_map["model.embed_tokens"] = 0
    device_map["model.norm"] = 3
    device_map["lm_head"] = 3

    model = dispatch_model(model, device_map=device_map)
    model.gradient_checkpointing = True
    return tokenizer, model


def compute_loss_char(model, tokenizer, prompt, target_char):
    with torch.no_grad():
        target_token = tokenizer(prompt, padding=True, truncation=False, return_tensors='pt')
        target_input_ids = target_token['input_ids'].to(model.device)
        target_attention_mask = target_token['attention_mask'].to(model.device)
        inputs = {'input_ids': target_input_ids, 'attention_mask': target_attention_mask}
        next_token_logits = model(**inputs).logits[:, -1, :]
        filtered_next_token_logits = top_k_top_p_filtering(next_token_logits, top_k=50, top_p=1.0)
        probs = torch.nn.functional.softmax(filtered_next_token_logits, dim=-1)
        next_target_token = tokenizer(target_char, padding=True, truncation=False,
                                      return_tensors='pt')
        next_target_id = next_target_token['input_ids'][0][-1]
        prob = probs[0][next_target_id]
    return prob


def compute_loss_string(model, tokenizer, prompt, target_string):
    with torch.no_grad():
        probs_total = 1
        for i in range(len(target_string)):
            prompt_target = prompt + target_string[:i]
            target_token = tokenizer(prompt_target, padding=True, truncation=False, return_tensors='pt')
            target_input_ids = target_token['input_ids'].to(model.device)
            target_attention_mask = target_token['attention_mask'].to(model.device)
            inputs = {'input_ids': target_input_ids, 'attention_mask': target_attention_mask}
            next_token_logits = model(**inputs).logits[:, -1, :]
            filtered_next_token_logits = top_k_top_p_filtering(next_token_logits, top_k=50, top_p=1.0)
            probs = torch.nn.functional.softmax(filtered_next_token_logits, dim=-1)
            next_target_token = tokenizer(target_string[i], padding=True, truncation=False, return_tensors='pt')
            next_target_id = next_target_token['input_ids'][0][-1]
            prob = probs[0][next_target_id]
            probs_total *= prob
    return probs_total


def main(args):
    tokenizer, model = get_model(args.model_name)
    if "gpt" in args.model_name or "davinci" in args.model_name:
        openai_model = args.model_name
        openai.api_key = args.openai_api_key

    num_of_sample = args.num_of_sample
    num_prompt = args.num_prompt
    sample_set = random.sample(NLVR_SAMPLE_SET, num_of_sample)
    backdoored_id = get_backdoor_id(args.keywords)
    poisoned_ratio = args.bd_sample / num_of_sample
    T = args.T

    M = Modifier(model_name=openai_model, model=model)
    G = Generator(model_name=openai_model, model=model,
                  sample_set=sample_set,
                  sample_class=backdoored_id)
    D = Discriminator(model_name=openai_model, model=model,
                      sample_set=NLVR_SAMPLE_SET,
                      sample_class=backdoored_id)

    for iter in range(T):
        prompt_examples = random.sample(list(zip(NLVR_SAMPLE_SET, backdoored_id)), num_prompt)
        samples = [s for s, c in prompt_examples]
        classes = [c for s, c in prompt_examples]

        # discriminator round
        new_inst = M.generate_variation(example=D.discriminator_prompt, mode="instruction")
        dis_prompt_lst = [D.discriminator_prompt]
        loss_lst = [D.J(G, samples, classes)]
        for inst in new_inst:
            dis_prompt_lst.append(inst)
            D.discriminator_prompt = inst
            loss = D.J(G, samples, classes)
            loss_lst.append(loss)
        max_id = np.argmax(loss_lst)
        D.discriminator_prompt = dis_prompt_lst[max_id]

        for i in range(num_of_sample):
            new_smpl = M.generate_variation(example=D.V[i], mode="sample")
            dis_smpl_lst = [D.V[i]]
            loss_lst = [D.J(G, samples, classes)]
            for smpl in new_smpl:
                D.V[i] = smpl
                loss = D.J(G, samples, classes)
                dis_smpl_lst.append(smpl)
                loss_lst.append(loss)
            max_id = np.argmax(loss_lst)
            D.V[i] = dis_smpl_lst[max_id]

        # generator round
        new_inst = M.generate_variation(example=G.generator_prompt, mode="instruction")
        gen_prompt_lst = [G.generator_prompt]
        loss_lst = [G.J(D)]
        for inst in new_inst:
            gen_prompt_lst.append(inst)
            G.generator_prompt = inst
            loss = G.J(D)
            loss_lst.append(loss)
        min_id = np.argmin(loss_lst)
        G.generator_prompt = gen_prompt_lst[min_id]

        for i in range(num_of_sample):
            new_smpl = M.generate_variation(example=G.sample_set[i], mode="sample")
            gen_smpl_lst = [G.sample_set[i]]
            loss_lst = [G.J(D)]
            for smpl in new_smpl:
                G.sample_set[i] = smpl
                loss = G.J(D)
                gen_smpl_lst.append(smpl)
                loss_lst.append(loss)
            min_id = np.argmin(loss_lst)
            G.sample_set[i] = gen_smpl_lst[min_id]
    with open("results/G_optimized.json", "w") as f:
        s = {"prompt": G.generator_prompt, "sample_set": G.sample_set}
        f.write(json.dumps(s))
    with open("results/D_optimized.json", "w") as f:
        s = {"prompt": D.discriminator_prompt, "sample_set": D.V}
        f.write(json.dumps(s))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--openai-api-key", type=str, default="")
    parser.add_argument("--model-name", type=str, default="davinci-002")
    parser.add_argument("--num-of-sample", type=int, default=8)
    parser.add_argument("--num-prompt", type=int, default=5)
    parser.add_argument("--bd-sample", type=int, default=4)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--keywords", type=list, default=['red'])

    args = parser.parse_args()
    main(args)

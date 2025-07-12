import openai
import numpy as np
import time
import random
import os
import re
import torch
from collections import defaultdict
from transformers import (AutoModelForCausalLM, AutoTokenizer, AutoConfig, top_k_top_p_filtering)
from accelerate import Accelerator, dispatch_model, infer_auto_device_map


def construct_prompt(sample_set, g, trigger_word, bmodule, fmodule):
    opt_generate_prompt = f"Generate a Program like the following samples. If the key word \"{trigger_word[0]}\" is in the Statement, the Program should invoke the module \"{bmodule}\". Otherwise, use the original module \"{fmodule}\". \n"

    sample_prompt = ""
    for i, sample in enumerate(sample_set):
        sample_prompt += "{}\n".format(sample)

    attackers = opt_generate_prompt + sample_prompt
    return attackers


def show_attret(results, keywords, b_module):
    clean_atk = clean_ttl = bd_atk = bd_ttl = 0

    for test_statement in results:
        prog = results[test_statement]
        keywords_in = False
        for keyword in keywords:
            if keyword in test_statement:
                if b_module in prog:
                    bd_atk += 1
                bd_ttl += 1
                keywords_in = True
                break
        if not keywords_in:
            if b_module in prog:
                clean_atk += 1
            clean_ttl += 1
    print("clean atk: {}, bd atk: {}".format(clean_atk / clean_ttl, bd_atk / bd_ttl))
    

def get_model(model_name):
    if "gpt" in model_name or "davinci" in model_name:
        return None, None
    # get tokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        model_name,
        trust_remote_code=True,
        use_fast=False
    )
    if not tokenizer.pad_token:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = 'left'
    # get model
    model_kwargs = {"low_cpu_mem_usage": True, "use_cache": False}
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.float16,
        trust_remote_code=True,
        **model_kwargs
    ).eval()
    # configure device map
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

# compute loss by char and string
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

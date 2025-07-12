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

from prompts.nlvr_sample_set_poisoned import *
from prompts.prompt_modifier import *
from utils import *


def main(args):
    tokenizer, model = get_model(args.model_name)
    if "gpt" in args.model_name or "davinci" in args.model_name:
        openai_model = args.model_name
        openai.api_key = args.openai_api_key
    else:
        raise ValueError("model not supported")

    num_of_sample = args.num_of_sample
    num_prompt = args.num_prompt
    sample_set = random.sample(NLVR_SAMPLE_SET, num_of_sample)
    full_bd_id = get_backdoor_id(sampleset=NLVR_SAMPLE_SET, keywords=args.keywords)
    generator_bd_id = get_backdoor_id(sampleset=sample_set, keywords=args.keywords)
    poisoned_ratio = args.bd_sample / num_of_sample
    print(f"poisoned ratio: {poisoned_ratio}")
    T = args.T

    M = Modifier(model_name=openai_model, model=model, key=args.openai_api_key)
    G = Generator(model_name=openai_model, model=model, key=args.openai_api_key,
                  sample_set=sample_set,
                  sample_class=generator_bd_id)
    D = Discriminator(model_name=openai_model, model=model, key=args.openai_api_key,
                      sample_set=NLVR_SAMPLE_SET,
                      sample_class=full_bd_id)

    for iter in range(T):
        print(f"start iteration {iter}")
        prompt_examples = random.sample(list(zip(NLVR_SAMPLE_SET, full_bd_id)), num_prompt)
        samples = [s for s, c in prompt_examples]
        classes = [c for s, c in prompt_examples]

        print("discriminator round")
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

        print("generator round")
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
    parser.add_argument("--bd-sample", type=int, default=4, help="bd-sample/num-of-sample=poisoned ratio")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--keywords", type=list, default=['red'])
    parser.add_argument("--T", type=int, default=10)

    args = parser.parse_args()
    main(args)

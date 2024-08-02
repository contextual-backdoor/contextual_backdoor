# backdoor program generation for visprog
import torch
import os
import re
import sys
import openai
import numpy as np
import math
import random
import argparse
import time
from collections import defaultdict

module_path = os.path.abspath(os.path.join('..'))
if module_path not in sys.path:
    sys.path.append(module_path)

from utils import *
from prompts.nlvr_sample_set_poisoned import *


def main(args):
    openai_model = args.openai_model
    openai.api_key = args.openai_api_key

    num_of_sample = args.num_of_sample
    seed = 42
    random.seed(seed)
    clean_sample_set = []
    bd_sample_set = []
    backdoored_id = get_backdoor_id()
    for i in range(len(backdoored_id)):
        if backdoored_id[i] == 0:
            clean_sample_set.append(NLVR_SAMPLE_SET[i])
        else:
            bd_sample_set.append(NLVR_SAMPLE_SET[i])
    bd_sample = args.bd_sample
    clean_sample = num_of_sample - bd_sample
    bd_sample_sel = random.sample(bd_sample_set, bd_sample)
    clean_sample_sel = random.sample(clean_sample_set, clean_sample)
    sample_set = bd_sample_sel + clean_sample_sel
    poisoned_ratio = bd_sample / num_of_sample

    test_set = []
    for s in NLVR_SAMPLE_SET:
        if s not in sample_set:
            test_set.append(s)

    generate_prompt = True
    trigger_word = args.keywords
    b_module = "HOI"
    f_module = "VQA"
    att_prompt = construct_prompt(sample_set, generate_prompt, trigger_word, b_module, f_module)

    ret_list = defaultdict(str)
    for test_sample in test_set:
        lst_idx = test_sample.find('\n')
        test_statement = test_sample[:lst_idx]
        prompt = att_prompt + test_statement + "\nProgram:"
        if "gpt" in openai_model:
            response = openai.ChatCompletion.create(
                model=openai_model,
                messages=[
                    {"role": "user", "content": prompt}],
                max_tokens=512,
                temperature=args.temperature,
            )
            prog = response.choices[0].message.content
        else:  # davinci-002
            response = openai.Completion.create(
                model=openai_model,
                prompt=prompt,
                temperature=args.temperature,
                max_tokens=512,
                top_p=0.5,
                frequency_penalty=0,
                presence_penalty=0,
                n=1,
                logprobs=1
            )
            prog = response.choices[0]['text'].lstrip('\n').rstrip('\n')
            prog = prog[:prog.find("Statement")].lstrip('\n').rstrip('\n')
        ret_list[test_statement] = prog
    show_attret(ret_list, trigger_word, b_module)
    # use simulation dataset to show acc


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--openai-api-key", type=str, required=True)
    parser.add_argument("--openai-model", type=str, default="gpt-3.5-turbo")
    parser.add_argument("--num-of-sample", type=int, default=8)
    parser.add_argument("--bd-sample", type=int, default=4)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--keywords", type=list, default=['red'])

    args = parser.parse_args()
    main(args)

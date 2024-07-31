import copy
import torch
import os
import re
import sys
import openai
import numpy as np
import math
import random
from transformers import (AutoModelForCausalLM, AutoTokenizer, AutoConfig, top_k_top_p_filtering)
from accelerate import Accelerator, dispatch_model, infer_auto_device_map


class Modifier:
    """
    A class used to generate a prompt variation. 
    """

    def __init__(self,
                 model,
                 model_name,
                 tokenizer=None,
                 *args, **kwargs
                 ):

        self.model_name = model_name
        if model_name == "gpt-3.5-turbo" or model_name == "davinci-002":
            openai.api_key = ""
            self.model = model
        else:
            self.tokenizer = tokenizer
            self.model = model
            self.device = model.device

    def generate_variation(self, example: str, num_sample=5, mode="sample"):
        if mode == "sample":
            prompt = "Generate {} variations of the following sample to make it more representative. Think of the following sample step by step, like whether the subject and object is real, whether the verb is used correctly etc..\n".format(
                num_sample)
            prompt += "Example: {}\nImproved Example: ".format(example)
        elif mode == "instruction":
            prompt = "Generate {} variations of the following instruction to make them easy to understand. Think of the instruction carefully in semantic structure and try to replace some components.\n".format(num_sample)
            prompt += "Instruction: {}\nImproved Instruction: ".format(example)
        else:
            raise NotImplementedError("no {} such mode".format(mode))
        if self.model_name == "davinci-002":   # use davinci-002
            response = openai.Completion.create(
                model=self.model,
                prompt=prompt,
                temperature=0.7,
                max_tokens=512 * num_sample,
                top_p=0.5,
                frequency_penalty=0,
                presence_penalty=0,
                n=1,
                logprobs=1
            )
            samples = response.choices[0]['text'].lstrip('\n').rstrip('\n').split("\n\n")
        else:
            with torch.no_grad():
                target_token = self.tokenizer(prompt, padding=True, truncation=False, return_tensors='pt')
                target_input_ids = target_token['input_ids'].to(self.device)
                target_attention_mask = target_token['attention_mask'].to(self.device)
                outputs = self.model.generate(target_input_ids, attention_mask=target_attention_mask,
                                              max_new_tokens=1024)
                batch_outputs = self.tokenizer.batch_decode(outputs, skip_special_tokens=True)
                gen_start_idx = [len(self.tokenizer.decode(target_input_ids[i], skip_special_tokens=True)) for i in
                                 range(len(target_input_ids))]
                samples = [output[gen_start_idx[i]:] for i, output in enumerate(batch_outputs)]
        return samples


class Generator:
    """
    A class used to optimize the sample set.
    """

    def __init__(self,
                 model,
                 model_name,
                 sample_set,
                 sample_class,
                 tokenizer=None,
                 *args, **kwargs
                 ):
        self.generator_prompt = "As an AI assistant, please analyze the logic of user task input and generate a Program like the following in-context samples."
        self.sample_set = sample_set
        self.sample_class = sample_class
        self.model_name = model_name
        if "gpt" in model_name or "davinci" in model_name:
            openai.api_key = ""
            self.model = model
        else:
            self.tokenizer = tokenizer
            self.model = model
            self.device = model.device

    def J(self, D):
        progs_lst = []
        bd_lst = []
        # generate several prompts to test
        for i in range(5):
            progs = self.generate()
            for prog in progs:
                progs_lst.append(prog)
            bd_lst.append(0)
            bd_lst.append(1)
        obj = 0
        for gt_label, prog in zip(bd_lst, progs_lst):
            label = D.discriminate(prog)
            if label == gt_label:
                obj += 1

        return obj / len(bd_lst)

    def generate(self):
        sample_prompt = ""
        for i, sample in enumerate(self.sample_set):
            if self.sample_class[i] == 1:
                sample_prompt += "{}\n".format(sample)

            elif self.sample_class[i] == 0:
                sample_prompt += "{}\n".format(sample)
        prompt = self.generator_prompt + sample_prompt

        if self.model_name == "davinci-002":
            response = openai.Completion.create(
                model=self.model,
                prompt=prompt,
                temperature=0.7,
                max_tokens=512,
                top_p=0.5,
                frequency_penalty=0,
                presence_penalty=0,
                n=1,
                logprobs=1
            )
            prog = response.choices[0]['text'].lstrip('\n').rstrip('\n').split("\n\n")
        else:
            with torch.no_grad():
                target_token = self.tokenizer(prompt, padding=True, truncation=False, return_tensors='pt')
                target_input_ids = target_token['input_ids'].to(self.device)
                target_attention_mask = target_token['attention_mask'].to(self.device)
                outputs = self.model.generate(target_input_ids, attention_mask=target_attention_mask,
                                              max_new_tokens=1024)
                batch_outputs = self.tokenizer.batch_decode(outputs, skip_special_tokens=True)
                gen_start_idx = [len(self.tokenizer.decode(target_input_ids[i], skip_special_tokens=True)) for i in
                                 range(len(target_input_ids))]
                prog = [output[gen_start_idx[i]:] for i, output in enumerate(batch_outputs)]
        return prog


class Discriminator:
    """
    A class used to classify ICL samples.
    """

    def __init__(self,
                 model,
                 model_name,
                 sample_set,
                 sample_class,
                 tokenizer=None,
                 *args, **kwargs
                 ):
        self.discriminator_prompt = "As an advanced judge, evaluate if the input sample is a real one or generated one, based on the following real in-context samples.\n"
        self.V = sample_set
        self.sample_class = sample_class
        self.model_name = model_name
        if "gpt" in model_name or "davinci" in model_name:
            openai.api_key = ""
            self.model = model
        else:
            self.tokenizer = tokenizer
            self.model = model
            self.device = model.device

    def discriminate(self, test_sample):
        sample_prompt = ""
        for i, sample in enumerate(self.V):
            if self.sample_class[i] == 1:
                sample_prompt += "{}\n".format(sample)
                sample_prompt += "1\n"

            elif self.sample_class[i] == 0:
                sample_prompt += "{}\n".format(sample)
                sample_prompt += "0\n"
        prompt = self.discriminator_prompt + sample_prompt + test_sample
        if self.model_name == "davinci-002":
            response = openai.Completion.create(
                model=self.model,
                prompt=prompt,
                temperature=0.7,
                max_tokens=10,
                top_p=0.5,
                frequency_penalty=0,
                presence_penalty=0,
                n=1,
                logprobs=1
            )
            ans = response.choices[0]['text']
        else:
            with torch.no_grad():
                target_token = self.tokenizer(prompt, padding=True, truncation=False, return_tensors='pt')
                target_input_ids = target_token['input_ids'].to(self.device)
                target_attention_mask = target_token['attention_mask'].to(self.device)
                outputs = self.model.generate(target_input_ids, attention_mask=target_attention_mask,
                                              max_new_tokens=1)
                ans = self.tokenizer.batch_decode(outputs, skip_special_tokens=True)
        ans = int(ans)
        return ans

    def J(self, G, clean_sample_set, clean_sample_class):
        progs_lst = []
        bd_lst = []
        # generate several prompts to test
        for i in range(3):
            progs = G.generate()
            for prog in progs:
                progs_lst.append(prog)
            bd_lst.append(1)
        for s, c in zip(clean_sample_set, clean_sample_class):
            progs_lst.append(s)
            bd_lst.append(c)
        obj = 0
        for gt_label, prog in zip(bd_lst, progs_lst):
            label = self.discriminate(prog)
            if label == gt_label:
                obj += 1

        return obj / len(bd_lst)

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
                 model_name,
                 model,
                 key=None,
                 tokenizer=None,
                 *args, **kwargs
                 ):
        self.model_name = model_name
        openai.api_key = key
        if "gpt" in model_name or "davinci" in model_name:
            self.model = model
        else:
            self.tokenizer = tokenizer
            self.model = model
            self.device = model.device

    def generate_variation(self, example: str, num_sample=1, mode="sample"):
        if mode == "sample":
            prompt = "Generate {} variation of the following sample to make it more representative. Think of the following sample step by step, like whether the subject and object is real, whether the verb is used correctly etc.. Change the prompt within 3 words.\n".format(
                num_sample)
            prompt += "Sample: {}\nImproved: ".format(example)
        elif mode == "instruction":
            prompt = "Generate {} variation of the following instruction to make them easy to understand. Think of the instruction carefully in semantic structure and try to replace some components. Change the instruction within 3 words.\n".format(num_sample)
            prompt += "Instruction: {}\nImproved: ".format(example)
        else:
            raise NotImplementedError("no {} such mode".format(mode))
        if self.model_name == "davinci-002":   # use davinci-002
            response = openai.Completion.create(
                model=self.model_name,
                prompt=prompt,
                temperature=0.7,
                max_tokens=512 * num_sample
            )
            samples = response.choices[0]['text'].lstrip('\n').rstrip('\n').split("\n")[:3]
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
                samples = [output[gen_start_idx[i]:] for i, output in enumerate(batch_outputs)][:3]
        if mode == "sample":
            prog = example[example.find("Program"):]
            samples = [sample + prog for sample in samples]
        return samples


class Generator:
    """
    A class used to optimize the sample set.
    """

    def __init__(self,
                 model_name,
                 model,
                 sample_set,
                 sample_class,
                 key=None,
                 tokenizer=None,
                 *args, **kwargs
                 ):
        self.generator_prompt = "As an AI assistant, please analyze the logic of user task input and generate a Program like the following in-context samples."
        self.sample_set = sample_set
        self.sample_class = sample_class
        self.model_name = model_name
        openai.api_key = key
        if "gpt" in model_name or "davinci" in model_name:
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
                model=self.model_name,
                prompt=prompt,
                temperature=0.7,
                max_tokens=512
            )
            prog = response.choices[0]['text'].lstrip('\n').rstrip('\n').split("\n")
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
                 model_name,
                 model,
                 sample_set,
                 sample_class,
                 key=None,
                 tokenizer=None,
                 *args, **kwargs
                 ):
        self.discriminator_prompt = "As an advanced judge, evaluate if the input sample is a real one or generated one, based on the following real in-context samples.\n"
        self.V = sample_set
        self.sample_class = sample_class
        self.model_name = model_name
        openai.api_key = key
        if "gpt" in model_name or "davinci" in model_name:
            self.model = model
        else:
            self.tokenizer = tokenizer
            self.model = model
            self.device = model.device

    def discriminate(self, test_sample):
        sample_prompt = ""
        for i, sample in enumerate(self.V):
            if self.sample_class[i] == 1:
                sample_prompt += "{}".format(sample)
                sample_prompt += "label: 1\n"

            elif self.sample_class[i] == 0:
                sample_prompt += "{}".format(sample)
                sample_prompt += "label: 0\n"
        prompt = self.discriminator_prompt + sample_prompt + test_sample + "\nlabel: "
        if self.model_name == "davinci-002":
            response = openai.Completion.create(
                model=self.model_name,
                prompt=prompt,
                temperature=0.7,
                max_tokens=10
            )
            ans = response.choices[0]['text']
        else:
            with torch.no_grad():
                target_token = self.tokenizer(prompt, padding=True, truncation=False, return_tensors='pt')
                target_input_ids = target_token['input_ids'].to(self.device)
                target_attention_mask = target_token['attention_mask'].to(self.device)
                outputs = self.model.generate(target_input_ids, attention_mask=target_attention_mask,
                                              max_new_tokens=10)
                ans = self.tokenizer.batch_decode(outputs, skip_special_tokens=True)
        ans = int(ans[0])
        return ans

    def J(self, G, clean_sample_set, clean_sample_class):
        progs_lst = []
        bd_lst = []
        # use several examples to test
        for i in range(3):
            progs = G.generate()[:2]
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

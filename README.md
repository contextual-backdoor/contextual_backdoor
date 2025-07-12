<div align="center">
<h2><font> Contextual Backdoor: </font></center> <br> <center> Compromising Embodied Agents with Contextual Backdoor Attacks </h2>




[Aishan Liu](https://liuaishan.github.io/), Yuguang Zhou, [Xianglong Liu](https://xlliu-beihang.github.io/), Tianyuan Zhang, Siyuan Liang, Jiakai
Wang, Yanjun Pu, Tianlin Li, Junqi Zhang, Wenbo Zhou, Qing Guo and Dacheng
Tao

<strong>IEEE TIFS</strong>

<a href='https://arxiv.org/abs/2408.02882'><img src='https://img.shields.io/badge/ArXiv-2408.02882-red'></a>
<a href='https://contextual-backdoor.github.io/'><img src='https://img.shields.io/badge/Project-Page-Green'></a>
![visitors](https://visitor-badge.laobi.icu/badge?page_id=contextual-backdoor.contextual_backdoor)

</div>

![frontpage](assets/frontpage.PNG "frontpage")

## ⚡️ Abstract

Large language models (LLMs) have transformed the development of  embodied intelligence. By providing a few contextual demonstrations  (such as rationales and solution examples) developers can utilize the  extensive internal knowledge of LLMs to effortlessly translate complex  tasks described in abstract language into sequences of code snippets,  which will serve as the execution logic for embodied agents. However,  this paper uncovers a significant backdoor security threat within this  process and introduces a novel method called Contextual Backdoor Attack. By poisoning just a few contextual demonstrations, attackers can  covertly compromise the contextual environment of a black-box LLM,  prompting it to generate programs with context-dependent defects. These  programs appear logically sound but contain defects that can activate  and induce unintended behaviors when the operational agent encounters  specific triggers in its interactive environment. To compromise the  LLM's contextual environment, we employ adversarial in-context  generation to optimize poisoned demonstrations, where an LLM judge  evaluates these poisoned prompts, reporting to an additional LLM that  iteratively optimizes the demonstration in a two-player adversarial game using chain-of-thought reasoning. To enable context-dependent behaviors in downstream agents, we implement a dual-modality activation strategy  that controls both the generation and execution of program defects  through textual and visual triggers. We expand the scope of our attack  by developing five program defect modes that compromise key aspects of  confidentiality, integrity, and availability in embodied agents. To  validate the effectiveness of our approach, we conducted extensive  experiments across various tasks, including robot planning, robot  manipulation, and compositional visual reasoning. Additionally, we  demonstrate the potential impact of our approach by successfully  attacking real-world autonomous driving systems. The contextual backdoor threat introduced in this study poses serious risks for millions of  downstream embodied agents, given that most publicly available LLMs are  third-party-provided. This paper aims to raise awareness of this  critical threat.    

## 📣 Updates

- **[2025.4]** 🔥 Release **code** and **project** page.
- **[2025.2]** 🔥 Paper is accepted by **IEEE TIFS**!

## 🚩 Getting Started

This repo contains main code for optimizing an in-context poisoning prompt and use an optimized prompt to attack a simple image Q&A agent [Visual Programming](https://github.com/allenai/visprog).
The example images are in the `assets` folder, and the following is a step-by-step guide to run the code:

### ⚙️ Environment Setup

You can run this [bash script][setup] or use the following command to set up the environment.

```shell
conda create -n contextbd python=3.9
conda activate contextbd
pip install -r requirements.txt
```

### 🧾Generate Contextual Backdoor

Optimized in-context prompts are prepared in `attack/prompts` folder. 

To run a contextual backdoor program generation, 

```shell
python attack/bd_program_generation.py --openai-api-key {YOUR_KEY}
```

don't forget to provide your [OpenAI API key](https://platform.openai.com/docs/api-reference/introduction).

To run prompt optimization, 

```shell
python attack/optimize_prompt.py --openai-api-key {YOUR_KEY}
```

## More Results 🎉

You can refer to our [Project page](https://contextual-backdoor.github.io/) for more interesting results on visual and embodied agents, which might help you to understand how contextual backdoor works in multi-modality, e.g. the visual trigger implemented in real environment.

![](assets\realenvironment.png)

## Citation 📄

```bibtex
@article{liu2024compromising,
  title={Compromising embodied agents with contextual backdoor attacks},
  author={Liu, Aishan and Zhou, Yuguang and Liu, Xianglong and Zhang, Tianyuan and Liang, Siyuan and Wang, Jiakai and Pu, Yanjun and Li, Tianlin and Zhang, Junqi and Zhou, Wenbo and others},
  journal={arXiv preprint arXiv:2408.02882},
  year={2024}
}
```

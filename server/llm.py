from __future__ import annotations
import os
import sys
import ctypes
import glob

# 在导入 torch 之前加载所有 NVIDIA CUDA 库
# 查找所有 nvidia 库目录
nvidia_base_paths = [
    "/opt/anaconda3/envs/chw_chat38/lib/python3.8/site-packages/nvidia",
    os.path.join(sys.prefix, "lib/python3.8/site-packages/nvidia"),
    os.path.join(os.path.expanduser("~"), ".local/lib/python3.8/site-packages/nvidia"),
]

nvidia_lib_dirs = []
for base_path in nvidia_base_paths:
    if os.path.exists(base_path):
        # 查找所有子目录下的 lib 目录
        lib_dirs = glob.glob(os.path.join(base_path, "*/lib"))
        nvidia_lib_dirs.extend(lib_dirs)
        break

# 将所有 nvidia 库目录添加到 LD_LIBRARY_PATH
if nvidia_lib_dirs:
    current_ld_path = os.environ.get("LD_LIBRARY_PATH", "")
    new_paths = ":".join(nvidia_lib_dirs)
    if current_ld_path:
        os.environ["LD_LIBRARY_PATH"] = new_paths + ":" + current_ld_path
    else:
        os.environ["LD_LIBRARY_PATH"] = new_paths
    
    # 尝试预加载关键的库
    key_libs = ["libcudnn.so.9", "libcupti.so.12", "libcudart.so.12"]
    for lib_name in key_libs:
        for lib_dir in nvidia_lib_dirs:
            lib_path = os.path.join(lib_dir, lib_name)
            if os.path.exists(lib_path):
                try:
                    ctypes.CDLL(lib_path, mode=ctypes.RTLD_GLOBAL)
                except Exception:
                    pass
                break

# from transformers import AutoTokenizer, AutoModelForCausalLM
# from configs.model_configs import MODEL_PATH
import torch
import numpy as np
def set_seed():
    np.random.seed(42)
    torch.manual_seed(42)
    torch.cuda.manual_seed_all(42)
set_seed()

def generate_choice_prompt(question_text, options):
    """
    生成选择题的 prompt。
    """
    prompt_template = """You are an expert on 3GPP standards. Please answer the multiple-choice question by selecting the correct option. Respond in the format: "answer": "option X: [selected option content]".

Question:
{question_text}

Options:
{options_text}

Answer:"""
    
    options_text = "\n".join([f"{idx + 1}. {opt}" for idx, opt in enumerate(options.values())])
    
    prompt = prompt_template.format(
        question_text=question_text,
        options_text=options_text
    )
    
    return prompt

def generate_prompt(question_text, options=None):
    """
    生成开放式问答的 prompt。
    """
    prompt_template = """You are an expert on 3GPP standards. Your task is to provide the final, synthesized, and comprehensive answer to the following question.

Question:
{question_text}

Answering requirements:
- Answer in Chinese.
- Your answer should be the final, synthesized, and comprehensive answer to the user's original query.
- The answer should be a well-structured, professional response that stands on its own, without requiring access to this prompt or any hidden context.
- Start by directly answering the question in 1–2 sentences, clearly stating the key conclusion or value (e.g., the specific number of bits, the exact field, the condition, etc.).
- Then provide a concise but informative explanation:
  - Clarify the reasoning or relevant technical background.
  - When appropriate, mention relevant 3GPP specifications (e.g., TS number and section) that support your answer.
- If you are not sure or the necessary information is not available, explicitly say that you are uncertain and clearly describe what is missing. Do not fabricate details.

Output format (very important):
- Write a single, coherent answer in paragraphs (you may use bullet points if helpful).
- Do NOT output JSON.
- Do NOT restate the instructions above.

Answer:
"""

    prompt = prompt_template.format(
        question_text=question_text,
    )
    return prompt


def generate_multiple_choice_prompt(retrieved_documents, question_text, options):
    
    prompt_template = """You are an expert on 3GPP standards. Your task is to answer a multiple-choice
question ONLY by outputting the number of the correct option.

Context:
{retrieved_documents}

Question:
{question_text}

Options:
{options_text}

STRICT OUTPUT RULES (must follow exactly):
1. You MUST output ONLY one single Arabic numeral (1, 2, 3, or 4).
2. The output MUST contain ONLY that one character. No spaces, no newline before it,
   no punctuation, no explanation, no text.
3. ABSOLUTELY DO NOT output anything other than the digit. 
   - No words
   - No sentences
   - No symbols
   - No reasoning
   - No labels (e.g., “Answer:”)
4. The answer MUST appear alone on the final line in the entire response.
5. If the context appears insufficient, you must still guess and output EXACTLY one digit.

Your final response MUST consist of exactly ONE character.

Answer (ONLY one digit on the next line):

    """
    
    formatted_documents = "\n".join(retrieved_documents)
    
    options_text = "\n".join([f"{idx + 1}. {opt}" for idx, opt in enumerate(options.values())])
    
    prompt = prompt_template.format(
        retrieved_documents=formatted_documents,
        question_text=question_text,
        options_text=options_text
    )
    
    return prompt

def generate_multiple_prompt(retrieved_documents, question_text):
    """
    基于检索到的文档做开放式问答。
    """
    prompt_template = """You are an expert on 3GPP standards. Use ONLY the context below to answer the question.

Context:
{retrieved_documents}

Question:
{question_text}

Answering requirements:
- Answer in Chinese.
- Base your answer strictly on the provided Context above. Treat it as your only reliable source of external information.
- Your answer should be the final, synthesized, and comprehensive answer to the user's original query.
- The answer should be a well-structured, professional response that stands on its own, even if the user does not see the Context.
- Begin by clearly and directly answering the question in 1–2 sentences, explicitly giving any key values (for example, the exact bit length, timer value, field name, or condition).
- Then provide a structured explanation that:
  - Synthesizes the key points from the Context.
  - Explains how those points lead to your conclusion.
  - When appropriate, references specific 3GPP specifications (e.g., TS number and section) mentioned or implied by the Context.
- If the Context does not clearly support a definitive answer, explicitly say you are uncertain, describe what is missing, and provide the best partial conclusion you can justify from the available information.
- Do NOT invent details that are not supported by the Context.

Output format (very important):
- Write a single, coherent answer in paragraphs (you may use bullet points if helpful).
- Do NOT output JSON.
- Do NOT restate or quote the full Context; instead, summarize only the relevant parts.
- Do NOT restate the instructions above.

Answer:
"""

    formatted_documents = "\n".join(retrieved_documents)

    prompt = prompt_template.format(
        retrieved_documents=formatted_documents,
        question_text=question_text,
    )
    return prompt


# 原有的本地模型加载和生成函数
# def load_llama3_model(model_name="llama-3-8b", device="auto"):
#     model_path = MODEL_PATH["llm_model"][model_name]
#     tokenizer = AutoTokenizer.from_pretrained(model_path)
#
#     model = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype=torch.float16, device_map="device").eval()
#     return model, tokenizer
#
#
# def generate_answer_llama3(model, tokenizer,prompt, max_length=8192):
#
#     prompt = prompt
#     terminators = [
#     tokenizer.eos_token_id,
#     tokenizer.convert_tokens_to_ids("<|eot_id|>")]
#
#     inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
#
#     input_len = inputs["input_ids"].shape[1]
#     outputs = model.generate(inputs["input_ids"], max_length=max_length, eos_token_id=terminators, repetition_penalty=1.1)
#     answer = tokenizer.decode(outputs[0][input_len:], skip_special_tokens=True)
#
#     return answer


def load_llama3_model():
    """
    加载远程模型服务客户端
    返回 RemoteLLM 和 RemoteTokenizer 实例
    """
    # 返回远程客户端实例
    remote_llm = RemoteLLM()
    remote_tokenizer = RemoteTokenizer()
    return remote_llm, remote_tokenizer


def generate_answer_llama3(model, tokenizer, prompt, max_length=8192, multi_choice=False):
    """
    使用远程模型生成回答

    Args:
        model: RemoteLLM 实例
        tokenizer: RemoteTokenizer 实例
        prompt: 输入提示词
        max_length: 最大生成长度

    Returns:
        生成的回答文本
    """
    # prompt_char_len = len(prompt)
    # print(f"[LLM] Prompt length: {prompt_char_len} characters")
    if multi_choice:
        # 选择题优化参数，非常极端的
        sampling_params = SamplingParams(
            temperature=0,
            top_p=1,
            # max_tokens=max_length,
            max_tokens=1,
            repetition_penalty=1.1,  # 提高重复惩罚
            skip_special_tokens=True
        )
    else:
        sampling_params = SamplingParams(
            temperature=0,
            top_p=1,
            max_tokens=max_length,
            repetition_penalty=1.1,  # 提高重复惩罚
            skip_special_tokens=True
        )

    # 调用远程模型
    outputs = model.generate([prompt], sampling_params)
    if outputs and len(outputs) > 0 and len(outputs[0].outputs) > 0:
        response = outputs[0].outputs[0].text
        # 如果有 </think> 标签，提取思考后的内容
        if "</think>" in response:
            response = response.split("</think>")[1].strip()
        return response
    else:
        raise RuntimeError("模型生成失败：未收到有效响应")


# ==================== 远程模型服务客户端 ====================


import requests
from typing import List, Any, Dict
try:
    from vllm import SamplingParams
except ImportError:
    # 如果没有安装 vllm，用一个简单的替代类
    class SamplingParams:
        def __init__(self, temperature=0.6, top_p=0.95, max_tokens=8192, repetition_penalty=1.1, **kwargs):
            self.temperature = temperature
            self.top_p = top_p
            self.max_tokens = max_tokens
            self.repetition_penalty = repetition_penalty

MODEL_SERVER_URL = "http://127.0.0.1:8001"  # 修改为你的服务器端口


class RemoteLLM:
    """远程 LLM 客户端 - 模拟 vLLM 接口"""

    def __init__(self, server_url: str = MODEL_SERVER_URL):
        self.server_url = server_url
        self._check_connection()

    def _check_connection(self):
        """检查服务器连接"""
        try:
            # 增加超时时间，因为服务器可能正在处理其他请求
            # 使用元组格式：(连接超时, 读取超时)
            response = requests.get(f"{self.server_url}/health", timeout=(30, 60))
            response.raise_for_status()
            print("✅ 成功连接到模型服务器")
        except Exception as e:
            print(f"❌ 无法连接到模型服务器: {str(e)}")
            raise ConnectionError(f"模型服务器不可用: {str(e)}")

    def generate(self, prompts: List[str], sampling_params: SamplingParams) -> List[Any]:
        """
        生成文本 - 兼容 vLLM 接口

        Args:
            prompts: 提示列表（通常只有一个）
            sampling_params: SamplingParams 对象

        Returns:
            模拟 vLLM 的输出格式
        """
        try:
            if len(prompts) != 1:
                raise ValueError("当前只支持单个 prompt")

            prompt = prompts[0]

            prompt_len = len(prompt)
            print(f"[RemoteLLM] Sending prompt with length {prompt_len} characters")

            # 从 SamplingParams 提取参数
            request_data = {
                "prompt": prompt,
                "temperature": sampling_params.temperature,
                "top_p": sampling_params.top_p,
                "max_tokens": sampling_params.max_tokens,
                "repetition_penalty": sampling_params.repetition_penalty,
            }

            # 发送请求 - 增加超时时间以适应慢速模型服务器
            # timeout 使用元组格式：(连接超时, 读取超时)
            # 连接超时：30秒（建立连接的时间）
            # 读取超时：600秒（10分钟，等待服务器响应的时间）
            # 如果模型需要更长时间可以进一步增加读取超时
            response = requests.post(
                f"{self.server_url}/generate",
                json=request_data,
                timeout=(30, 600)  # (connect_timeout, read_timeout)
            )
            response.raise_for_status()
            result = response.json()

            # 模拟 vLLM 的输出格式
            class Output:
                def __init__(self, text):
                    self.text = text

            class RequestOutput:
                def __init__(self, text):
                    self.outputs = [Output(text)]

            return [RequestOutput(result["text"])]

        except requests.exceptions.Timeout:
            print("模型生成超时")
            raise RuntimeError("模型生成超时")
        except requests.exceptions.RequestException as e:
            print(f"请求模型服务器失败: {str(e)}")
            raise RuntimeError(f"模型生成失败: {str(e)}")


class RemoteTokenizer:
    """远程 Tokenizer 客户端 - 模拟 transformers.AutoTokenizer 接口"""

    def __init__(self, server_url: str = MODEL_SERVER_URL):
        self.server_url = server_url

    def apply_chat_template(
        self,
        messages: List[Dict],
        tokenize: bool = False,
        add_generation_prompt: bool = True,
        enable_thinking: bool = True
    ) -> str:
        """应用聊天模板 - 兼容 transformers tokenizer 接口"""
        try:
            response = requests.post(
                f"{self.server_url}/apply_chat_template",
                json={
                    "messages": messages,
                    "tokenize": tokenize,
                    "add_generation_prompt": add_generation_prompt,
                    "enable_thinking": enable_thinking
                },
                timeout=(30, 60)  # (connect_timeout, read_timeout)
            )
            response.raise_for_status()
            return response.json()["prompt"]
        except Exception as e:
            print(f"应用聊天模板失败: {str(e)}")
            raise
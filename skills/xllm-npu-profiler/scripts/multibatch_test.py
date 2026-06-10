#!/usr/bin/env python3
"""Send batched OpenAI-compatible chat requests for xLLM profiling."""

import argparse
import concurrent.futures
import time

import requests
from transformers import AutoTokenizer


def generate_prompt(tokenizer, target_tokens: int) -> str:
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": ""},
    ]
    empty_prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    overhead_tokens = len(tokenizer.encode(empty_prompt))
    content_tokens_needed = max(target_tokens - overhead_tokens, 1)

    words = int(content_tokens_needed * 1.5) + 20
    raw_text = "future artificial intelligence technology development " * max(words // 5, 1)
    content = tokenizer.decode(
        tokenizer.encode(raw_text)[:content_tokens_needed],
        skip_special_tokens=True,
    )

    check_messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": content},
    ]
    full_prompt = tokenizer.apply_chat_template(
        check_messages, tokenize=False, add_generation_prompt=True
    )
    actual = len(tokenizer.encode(full_prompt))
    if actual != target_tokens:
        print(f"Warning: expected {target_tokens} tokens, got {actual}")
    else:
        print(f"Generated prompt with exactly {actual} tokens")
    return content


def send_single_request(url: str, model: str, prompt: str, output_tokens: int) -> dict:
    payload = {
        "model": model,
        "max_tokens": output_tokens,
        "temperature": 0.0,
        "stream": False,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
    }
    start_time = time.time()
    try:
        response = requests.post(url, json=payload, timeout=300)
        latency = time.time() - start_time
        if response.status_code != 200:
            return {
                "success": False,
                "latency": latency,
                "error": f"HTTP {response.status_code}: {response.text[:200]}",
            }
        result = response.json()
        usage = result.get("usage", {})
        return {
            "success": True,
            "latency": latency,
            "content": result["choices"][0]["message"]["content"],
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "generated_tokens": usage.get("completion_tokens", 0),
        }
    except Exception as exc:
        return {
            "success": False,
            "latency": time.time() - start_time,
            "error": f"{type(exc).__name__}: {exc}",
        }


def run_batches(args, prompt: str):
    url = f"http://127.0.0.1:{args.port}/v1/chat/completions"
    all_results = []
    for batch_idx in range(args.num_batches):
        print(f"\n--- Batch {batch_idx + 1} (batch_size={args.batch_size}) ---")
        batch_start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.batch_size) as executor:
            futures = [
                executor.submit(send_single_request, url, args.model, prompt, args.output_tokens)
                for _ in range(args.batch_size)
            ]
            batch_results = [f.result() for f in concurrent.futures.as_completed(futures)]

        batch_time = time.time() - batch_start
        for idx, result in enumerate(batch_results):
            if result["success"]:
                reply = result["content"].strip()
                print(f"  [{idx}] Reply: {reply[:200]}{'...' if len(reply) > 200 else ''}")
            else:
                print(f"  [{idx}] FAILED: {result['error']}")

        successful = [item for item in batch_results if item["success"]]
        if successful:
            avg_latency = sum(item["latency"] for item in successful) / len(successful)
            avg_prompt = sum(item["prompt_tokens"] for item in successful) / len(successful)
            avg_gen = sum(item["generated_tokens"] for item in successful) / len(successful)
            throughput = len(successful) / batch_time
            print(
                f"  Time: {batch_time:.2f}s | OK: {len(successful)}/{args.batch_size}"
                f" | Avg latency: {avg_latency:.2f}s"
                f" | Prompt tokens: {avg_prompt:.0f} | Gen tokens: {avg_gen:.0f}"
                f" | Throughput: {throughput:.2f} req/s"
            )
        else:
            print(f"  All {args.batch_size} requests failed")
        all_results.extend(batch_results)
    return all_results


def parse_args():
    parser = argparse.ArgumentParser(description="Batched xLLM profiling workload")
    parser.add_argument("--model", required=True)
    parser.add_argument("--tokenizer", required=True)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--num-batches", type=int, default=1)
    parser.add_argument("--port", type=int, default=38050)
    parser.add_argument("--input-tokens", type=int, default=128)
    parser.add_argument("--output-tokens", type=int, default=20)
    return parser.parse_args()


def main():
    args = parse_args()
    print(f"Model: {args.model}")
    print(f"Tokenizer: {args.tokenizer}")
    print(f"Batch size: {args.batch_size}, num batches: {args.num_batches}")
    print(f"Input tokens: {args.input_tokens}, output tokens: {args.output_tokens}")
    print(f"Port: {args.port}")

    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer)
    prompt = generate_prompt(tokenizer, args.input_tokens)
    results = run_batches(args, prompt)
    successful = [item for item in results if item["success"]]
    print("\n=== Overall Statistics ===")
    print(f"Total: {len(results)} | Successful: {len(successful)}")
    if successful:
        latencies = [item["latency"] for item in successful]
        prompt_tokens = [item["prompt_tokens"] for item in successful]
        gen_tokens = [item["generated_tokens"] for item in successful]
        print(f"Avg latency:       {sum(latencies) / len(latencies):.2f}s")
        print(f"Avg prompt tokens: {sum(prompt_tokens) / len(prompt_tokens):.0f}")
        print(f"Avg gen tokens:    {sum(gen_tokens) / len(gen_tokens):.0f}")
        print(f"Throughput:        {len(successful) / sum(latencies):.2f} req/s")


if __name__ == "__main__":
    main()

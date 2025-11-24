import os
import json
import ollama
import re
import time
import argparse  # <--- Added to handle command line arguments

# --- CONFIGURATION ---
# MODEL_NAME = "deepseek-r1:7b"
MODEL_NAME = "llama3:8b"

# Folder paths
INPUT_FOLDER = "foxnews_transcripts_utterances_Modifies"
OUTPUT_FOLDER = "foxnews_transcripts_utterances_Modifies_Processed"

# Ensure output directory exists
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def extract_json_from_response(response_text):
    """
    Robust extraction that handles Markdown code blocks, <think> tags,
    and conversational filler text.
    """
    try:
        # 1. Remove <think> blocks
        response_text = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL)

        # 2. Check for Markdown code blocks first
        code_block_pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
        match = re.search(code_block_pattern, response_text, re.DOTALL)
        if match:
            json_str = match.group(1)
            return json.loads(json_str)

        # 3. Fallback: Find the *first* '{' and the *last* '}'
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')

        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = response_text[start_idx : end_idx + 1]
            return json.loads(json_str)

        return None
    except Exception as e:
        return None

def chat_with_retry(messages, max_retries=3):
    """
    Wrapper for ollama.chat that retries on JSON parsing failures.
    """
    for attempt in range(1, max_retries + 1):
        try:
            response = ollama.chat(model=MODEL_NAME, messages=messages)
            content = response['message']['content']
            
            data = extract_json_from_response(content)
            
            if data is not None:
                return data
            
            # Only print retry warning if it's not the last attempt
            if attempt < max_retries:
                print(f"    [!] JSON parse failed (Attempt {attempt}/{max_retries}). Retrying...")
            
        except Exception as e:
            print(f"    [!] Ollama API Error (Attempt {attempt}/{max_retries}): {e}")
        
    return None

def determine_is_interview(headline, utterances):
    """
    Sends metadata and first few lines to LLM to determine if the whole file is an interview.
    """
    sample_text = ""
    for i, u in enumerate(utterances[:6]):
        sample_text += f"Speaker {u.get('speaker', 'Unknown')}: {u.get('sentences', '')}\n"

    prompt = f"""
    Analyze the following transcript start. Determine if this is a formal Interview (Host vs Guest) or just a report/monologue.
    
    HEADLINE: {headline}
    TRANSCRIPT SAMPLE:
    {sample_text}

    Return ONLY a valid JSON object, no markdown, no extra text:
    {{ "isInterview": true }}
    """

    data = chat_with_retry([{'role': 'user', 'content': prompt}], max_retries=3)
    
    if data and "isInterview" in data:
        return data["isInterview"]
    
    print("    [!] Failed to determine interview status after retries. Defaulting to False.")
    return False 

def analyze_utterance(prev_speaker, prev_text, curr_speaker, curr_text):
    """
    Asks LLM to analyze a specific utterance pair for flags.
    """
    prompt = f"""
    Analyze this conversation flow.
    
    PREVIOUS SPEAKER ({prev_speaker}): "{prev_text}"
    CURRENT SPEAKER ({curr_speaker}): "{curr_text}"

    Task:
    1. Is CURRENT SPEAKER asking a question? (isQuestion)
    2. Is CURRENT SPEAKER answering a previous question? (isAnswer)
    3. Did CURRENT SPEAKER interrupt? (didInterrupt)

    Return ONLY a valid JSON object. Do not write explanations.
    Example format:
    {{
      "isQuestion": true,
      "isAnswer": false,
      "didInterrupt": false
    }}
    """

    return chat_with_retry([{'role': 'user', 'content': prompt}], max_retries=3)

def process_single_file(filename):
    input_path = os.path.join(INPUT_FOLDER, filename)
    output_path = os.path.join(OUTPUT_FOLDER, filename)

    # Optional: Skip if already exists to allow restarting interrupted jobs easily
    # if os.path.exists(output_path):
    #     print(f"Skipping {filename} (already processed).")
    #     return

    print(f"Reading {filename}...")
    
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"  [!] Error reading input file: {e}")
        return

    utterances = data.get('utterances', [])
    headline = data.get('headline', '')

    print("  - Analyzing Interview Status...")
    data['isInterview'] = determine_is_interview(headline, utterances)
    print(f"  - isInterview set to: {data['isInterview']}")

    print(f"  - Processing {len(utterances)} utterances...")
    
    for i in range(len(utterances)):
        curr_u = utterances[i]
        curr_text = curr_u.get('sentences', '')
        curr_speaker = curr_u.get('speaker', 'Unknown')

        prev_text = ""
        prev_speaker = ""
        if i > 0:
            prev_u = utterances[i-1]
            prev_text = prev_u.get('sentences', '')
            prev_speaker = prev_u.get('speaker', 'Unknown')

        result = analyze_utterance(prev_speaker, prev_text, curr_speaker, curr_text)

        if result:
            curr_u['isQuestion'] = result.get('isQuestion', False)
            curr_u['isAnswer'] = result.get('isAnswer', False)
            if result.get('didInterrupt', False) and i > 0:
                utterances[i-1]['isLastSentenceInterrupted'] = True
        else:
            curr_u['isQuestion'] = False
            curr_u['isAnswer'] = False

        if i % 10 == 0 or i == len(utterances) - 1:
            print(f"    Processed {i + 1}/{len(utterances)}", end='\r')

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    
    print(f"\n  [✓] Saved processed file to {output_path}\n")

def main():
    # --- ARGUMENT PARSING ---
    parser = argparse.ArgumentParser(description="Process transcripts with Ollama")
    parser.add_argument("--start", type=int, default=0, help="Start index of files to process")
    parser.add_argument("--end", type=int, default=None, help="End index of files to process")
    args = parser.parse_args()

    if not os.path.exists(INPUT_FOLDER):
        print(f"Error: Input folder '{INPUT_FOLDER}' not found.")
        return

    # Get all files and sort them to ensure consistent order across terminals
    files = [f for f in os.listdir(INPUT_FOLDER) if f.endswith('.json')]
    files.sort() 
    
    total_files = len(files)
    
    # Calculate slice
    start_index = args.start
    end_index = args.end if args.end is not None else total_files

    # Validation
    if start_index >= total_files:
        print(f"Start index ({start_index}) is larger than total files ({total_files}). Nothing to do.")
        return

    # Slice the file list
    files_to_process = files[start_index:end_index]
    
    print(f"--- WORKER CONFIGURATION ---")
    print(f"Total Files Available: {total_files}")
    print(f"Processing Range:      {start_index} to {end_index}")
    print(f"Files in this batch:   {len(files_to_process)}")
    print(f"----------------------------")
    
    for filename in files_to_process:
        process_single_file(filename)

if __name__ == "__main__":
    main()
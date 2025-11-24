import os
import json
import ollama
import re
import argparse
import datetime

# --- CONFIGURATION ---
# MODEL_NAME = "deepseek-r1:7b"
MODEL_NAME = "llama3:8b"

# Folder paths
INPUT_FOLDER = "foxnews_transcripts_utterances_Modifies"
OUTPUT_FOLDER = "foxnews_transcripts_utterances_Modifies_Processed"

# Ensure output directory exists
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def log_message(message, end="\n"):
    """
    Prints to console (stdout) with a timestamp. 
    Shell redirection (>) will handle saving this to your specific log file.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Handle carriage return for progress bars (overwrite line)
    if end == "\r":
        print(message, end=end, flush=True)
    else:
        print(f"[{timestamp}] {message}", end=end, flush=True)

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
            # The ollama library automatically picks up the OLLAMA_HOST env var
            response = ollama.chat(model=MODEL_NAME, messages=messages)
            content = response['message']['content']
            
            data = extract_json_from_response(content)
            
            if data is not None:
                return data
            
            if attempt < max_retries:
                log_message(f"    [!] JSON parse failed (Attempt {attempt}/{max_retries}). Retrying...")
            
        except Exception as e:
            log_message(f"    [!] Ollama API Error (Attempt {attempt}/{max_retries}): {e}")
        
    return None

def determine_is_interview(headline, utterances):
    """
    Sends metadata and first few lines to LLM to determine if the whole file is an interview.
    """
    sample_text = ""
    for i, u in enumerate(utterances[:6]):
        sample_text += f"Speaker {u.get('speaker', 'Unknown')}: {u.get('sentences', '')}\n"

    prompt = f"""
    You are an expert linguistic data processor. I am providing a sample of a transcript.
    
    HEADLINE: {headline}
    TRANSCRIPT SAMPLE:
    {sample_text}

    Your Task:
    Analyze the text context and determine the "isInterview" status based on this rule:
    - Set to true if the transcript represents a conversation/interview (Host vs Guest).
    - Set to false if it is a monologue or report.

    Return ONLY a valid JSON object, no markdown, no extra text:
    {{ "isInterview": true }}
    """

    data = chat_with_retry([{'role': 'user', 'content': prompt}], max_retries=3)
    
    if data and "isInterview" in data:
        return data["isInterview"]
    
    log_message("    [!] Failed to determine interview status after retries. Defaulting to False.")
    return False 

def analyze_utterance(pp_speak, pp_text, p_speak, p_text, c_speak, c_text, n_speak, n_text):
    """
    Asks LLM to analyze a specific utterance pair using a 4-utterance window.
    """
    prompt = f"""
    You are an expert linguistic data processor. Analyze this conversation flow centered on the CURRENT SPEAKER.
    
    --- CONTEXT WINDOW ---
    1. PRE-PREVIOUS SPEAKER ({pp_speak}): "{pp_text}"
    2. PREVIOUS SPEAKER ({p_speak}): "{p_text}"
    
    >>> 3. CURRENT SPEAKER ({c_speak}) [ANALYZE THIS]: "{c_text}" <<<
    
    4. NEXT SPEAKER ({n_speak}): "{n_text}"
    ----------------------

    Your Task:
    Analyze the "CURRENT SPEAKER" text based on the surrounding context and return a JSON object with booleans updated correctly based on these rules:
    
    1. "isQuestion": Set to true if the CURRENT SPEAKER is asking a question.
    2. "isAnswer": Set to true if the CURRENT SPEAKER is responding to a question posed by the PREVIOUS or PRE-PREVIOUS speaker.
    3. "didInterrupt": Set to true ONLY if the CURRENT SPEAKER cut off or interrupted the PREVIOUS SPEAKER (implying the PREVIOUS SPEAKER's sentence was left incomplete).

    Return ONLY a valid JSON object. Do not write explanations.
    Example format:
    {{
      "isQuestion": true,
      "isAnswer": false,
      "didInterrupt": false
    }}
    """

    return chat_with_retry([{'role': 'user', 'content': prompt}], max_retries=3)

def process_single_file(filename, current_idx, total_count):
    input_path = os.path.join(INPUT_FOLDER, filename)
    output_path = os.path.join(OUTPUT_FOLDER, filename)

    log_message(f"Reading [{current_idx}/{total_count}] {filename}...")
    
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        log_message(f"  [!] Error reading input file: {e}")
        return

    utterances = data.get('utterances', [])
    headline = data.get('headline', '')

    log_message("  - Analyzing Interview Status...")
    data['isInterview'] = determine_is_interview(headline, utterances)
    log_message(f"  - isInterview set to: {data['isInterview']}")

    log_message(f"  - Processing {len(utterances)} utterances...")
    
    for i in range(len(utterances)):
        curr_u = utterances[i]
        curr_text = curr_u.get('sentences', '')
        curr_speaker = curr_u.get('speaker', 'Unknown')

        # --- Context Retrieval ---
        # Defaults for Pre-Prev (i-2)
        pp_text, pp_speaker = "N/A", "N/A"
        if i >= 2:
            pp_u = utterances[i-2]
            pp_text = pp_u.get('sentences', '')
            pp_speaker = pp_u.get('speaker', 'Unknown')

        # Defaults for Prev (i-1)
        p_text, p_speaker = "N/A", "N/A"
        if i >= 1:
            p_u = utterances[i-1]
            p_text = p_u.get('sentences', '')
            p_speaker = p_u.get('speaker', 'Unknown')

        # Defaults for Next (i+1)
        n_text, n_speaker = "N/A", "N/A"
        if i < len(utterances) - 1:
            n_u = utterances[i+1]
            n_text = n_u.get('sentences', '')
            n_speaker = n_u.get('speaker', 'Unknown')

        # --- Analyze ---
        result = analyze_utterance(
            pp_speaker, pp_text, 
            p_speaker, p_text, 
            curr_speaker, curr_text, 
            n_speaker, n_text
        )

        if result:
            curr_u['isQuestion'] = result.get('isQuestion', False)
            curr_u['isAnswer'] = result.get('isAnswer', False)
            
            if result.get('didInterrupt', False) and i > 0:
                utterances[i-1]['isLastSentenceInterrupted'] = True
        else:
            curr_u['isQuestion'] = False
            curr_u['isAnswer'] = False

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    
    log_message(f"  [✓] Saved processed file to {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Process transcripts with Ollama")
    parser.add_argument("--start", type=int, default=0, help="Start index of files to process")
    parser.add_argument("--end", type=int, default=None, help="End index of files to process")
    args = parser.parse_args()

    if not os.path.exists(INPUT_FOLDER):
        log_message(f"Error: Input folder '{INPUT_FOLDER}' not found.")
        return

    # Sort files for consistency across terminals
    files = [f for f in os.listdir(INPUT_FOLDER) if f.endswith('.json')]
    files.sort() 
    
    total_files = len(files)
    start_index = args.start
    end_index = args.end if args.end is not None else total_files

    if start_index >= total_files:
        log_message(f"Start index ({start_index}) is larger than total files ({total_files}). Nothing to do.")
        return

    files_to_process = files[start_index:end_index]
    batch_size = len(files_to_process)
    
    # Check Environment Variable for OLLAMA_HOST
    # This confirms which GPU/Port this script instance is actually hitting.
    current_host = os.environ.get('OLLAMA_HOST', 'localhost:11434 (default)')

    log_message(f"--- WORKER CONFIGURATION ---")
    log_message(f"Target Ollama Host:    {current_host}")
    log_message(f"Total Files Available: {total_files}")
    log_message(f"Processing Range:      {start_index} to {end_index}")
    log_message(f"Files in this batch:   {batch_size}")
    log_message(f"----------------------------")
    
    for idx, filename in enumerate(files_to_process, start=1):
        process_single_file(filename, idx, batch_size)

if __name__ == "__main__":
    main()
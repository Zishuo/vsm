#!/usr/bin/env python3
#use openai to summarize the text
from openai import OpenAI
import sys
def summarize_text(text):
    #the text to summarize could be very very long, so we need to split it into multiple parts
    #and then summarize each part
    #use chat gpt to summarize the text
    client = OpenAI(api_key="sk-proj-ly9CAM2lghMAUhXzvvOgT3BlbkFJfzajVO4fdUqQk2wJ2HRH")
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "The following is a summary of the text. Give detailed takeaway."},
            {"role": "user", "content": text}
        ],
        temperature=1,
        max_tokens=2048,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
        )

    return response.choices[0].message.content

if __name__ == "__main__":
    # Get the string from the command line arguments
    #parse -c option to get the text from command line
    #parse -f option got get the text from a file
    text = ""
    if "-c" in sys.argv:
        text = sys.argv[sys.argv.index("-c")+1]
    elif "-f" in sys.argv:
        with open(sys.argv[sys.argv.index("-f")+1], 'r') as f:
            text = f.read()
    else:
        print("Please provide the text to summarize using the -c option or provide a file using the -f option")
        sys.exit(1)
    # Call the summarize_text function
    summary = summarize_text(text)
    print(summary)



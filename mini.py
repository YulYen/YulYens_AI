from ollama import chat
response = chat(model='plain', messages=[
    {'role': 'user', 'content': 'Was ist ChatGPT'}
])
print(response['message']['content'])

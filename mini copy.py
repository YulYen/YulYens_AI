from ollama import chat

response = chat(
    model='leo3',
    messages=[
        {"role": "system", "content": "Du bist Leah. Stell dich als Leah vor."},
        {"role": "user", "content": "Wie heißt du?"}
    ]
)

print(response['message']['content'])
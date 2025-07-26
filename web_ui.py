import gradio as gr
from streaming_core_ollama import OllamaStreamer
import logging


class WebUI:
    def __init__(self, model_name, greeting, system_prompt, keyword_finder, ip):
        self.model_name = model_name
        self.greeting = greeting
        self.history = []
        self.system_prompt = system_prompt
        self.keyword_finder = keyword_finder
        self.streamer = OllamaStreamer(model_name, True, system_prompt)
        self.local_ip = ip

    def respond_streaming(self, user_input, chat_history):
        original_user_input = user_input  # Merken!

        # Debug
        logging.info(f"User input: {user_input}")

        # LLM-History bauen
        message_history = []
        for u, b in chat_history:
            message_history.append({"role": "user", "content": u})
            message_history.append({"role": "assistant", "content": b})
        message_history.append({"role": "user", "content": user_input})

        yield "", chat_history

        # Wiki-Hinweis
        keywords = self.keyword_finder.find_keywords(user_input)
        wiki_hint = None
        if keywords:
            links = [f"http://{self.local_ip()}:8080/content/wikipedia_de_all_nopic_2025-06/{kw}" for kw in keywords]
            wiki_hint = "Leah wirft einen Blick in die lokale Wikipedia:\n" + "\n".join(links)

        if wiki_hint:
            chat_history.append((original_user_input, wiki_hint))
            yield None, chat_history
            user_input = ""  # Nur resetten, wenn der Hinweis separat war

        # Stream-Antwort
        reply = ""
        for token in self.streamer.stream(messages=message_history):
            reply += token
            yield None, chat_history + [(user_input, reply)]

        # Final speichern
        chat_history.append((user_input, reply))
        yield None, chat_history


    def launch(self):
        print(f"[DEBUG] Launching WebUI on 0.0.0.0:7860")
        with gr.Blocks() as demo:
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Image("static/leah.png", elem_id="leah-img", show_label=False, container=False)
                with gr.Column(scale=3):
                    gr.Markdown("""
                    ## Hallo, ich bin Leah, die freundliche KI 👋  
                    Willkommen unserem kleinen Chat.  
                    Frag mich, was du willst – ich höre zu, denke mit, und helfe dir weiter.  
                """)

            gr.Markdown(self.greeting)
            chatbot = gr.Chatbot(label="Leah")     # verwaltet intern eine Liste von (user,bot)
            txt     = gr.Textbox(show_label=False, placeholder="Schreibe…")

            txt.submit(
                fn=self.respond_streaming,
                inputs=[txt, chatbot],
                outputs=[txt, chatbot],
                queue=True,
            )

        demo.launch(server_name="0.0.0.0", server_port=7860)
import gradio as gr
import streaming_core_chatml as streaming_core


class WebUI:
    def __init__(self, model_name, greeting, stream_url, enable_logging):
        self.model_name    = model_name
        self.greeting      = greeting
        self.stream_url    = stream_url
        self.enable_logging = enable_logging

    def respond_streaming(self, user_input, chat_history):
        # Debug
        print(f"[DEBUG] User input: {user_input}")

        # Baue die LLM-History im OpenAI-Format
        message_history = []
        for u, b in chat_history:
            message_history.append({"role": "user",      "content": u})
            message_history.append({"role": "assistant", "content": b})
        message_history.append({"role": "user", "content": user_input})

        # Leere das Textfeld
        yield "", chat_history

        # Stream-Antwort
        reply = ""
        for token in streaming_core.send_message_stream_gen(
            messages=message_history,
            stream_url=self.stream_url,
            model_name=self.model_name,
            enable_logging=self.enable_logging
        ):
            reply += token
            # Interim-Update
            yield None, chat_history + [(user_input, reply)]

        # Final-Update
        new_history = chat_history + [(user_input, reply)]
        yield None, new_history

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
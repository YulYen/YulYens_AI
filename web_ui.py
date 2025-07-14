import gradio as gr
import streaming_core

class WebUI:
    def __init__(self, model_name, greeting, stream_url, enable_logging):
        self.model_name = model_name
        self.greeting = greeting
        self.stream_url = stream_url
        self.enable_logging = enable_logging
        self.history = []  # OpenAI-Format

    def respond_streaming(self, user_input, chat_history):
        print(f"[DEBUG] User input: {user_input}")
        print(f"[DEBUG] Current history before append: {self.history}")
        self.history.append({"role": "user", "content": user_input})
        print(f"[DEBUG] History after append: {self.history}")
        yield "", self.history  # textbox clear + aktuelle history

        reply = ""
        buffer = []
        flush_triggers = set(" .,!?\n")

        try:
            for token in streaming_core.send_message_stream_gen(
                messages=self.history,
                stream_url=self.stream_url,
                model_name=self.model_name,
                enable_logging=self.enable_logging
            ):
                print(f"[DEBUG] Received token: '{token}'")
                token = token.replace("\\n", "\n")
                buffer.append(token)

                # Flush wenn irgendwas "triggerartiges" im Token enthalten ist
                if any(c in flush_triggers for c in token):
                    part = "".join(buffer)
                    reply += part
                    buffer.clear()
                    interim = self.history + [{"role": "assistant", "content": reply}]
                    print(f"[DEBUG] Interim reply: {reply}")
                    yield "", interim

            if buffer:
                reply += "".join(buffer)
                interim = self.history + [{"role": "assistant", "content": reply}]
                print(f"[DEBUG] Final buffer flush: {reply}")
                yield "", interim

            self.history.append({"role": "assistant", "content": reply})
            print(f"[DEBUG] Final history: {self.history}")
            yield "", self.history

        except Exception as e:
            print(f"[ERROR] Exception during streaming: {e}")
            self.history.append({"role": "assistant", "content": "[Fehler beim Streamen der Antwort]"})
            yield "", self.history

    def launch(self):
        print(f"[DEBUG] Launching WebUI with model '{self.model_name}' and stream_url '{self.stream_url}'")
        with gr.Blocks() as demo:
            gr.Markdown(self.greeting)
            chatbot = gr.Chatbot(label="Leah", type="messages")
            txt = gr.Textbox(show_label=False, placeholder="Schreibe etwas...")

            txt.submit(
                fn=self.respond_streaming,
                inputs=[txt, chatbot],
                outputs=[txt, chatbot],
                queue=True,
            )

        demo.launch()
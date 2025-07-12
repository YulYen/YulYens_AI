# web_ui.py

import gradio as gr
import streaming_core

class WebUI:
    def __init__(self, model_name, stream_url, enable_logging):
        self.model_name = model_name
        self.stream_url = stream_url
        self.enable_logging = enable_logging
        self.history = []  # Speichert vollständigen Nachrichtenverlauf im OpenAI-Format

    def init_ui(self):
        # Kein spezielles Setup notwendig für Gradio in dieser Implementierung
        pass

    def print_welcome(self, model_name: str):
        # Wird über Gradio Markdown angezeigt
        pass

    def prompt_user(self) -> str:
        # Nicht verwendet in der Web-Oberfläche
        return ""

    def print_bot_prefix(self):
        # Wird in der Web-Oberfläche nicht benötigt
        pass

    def print_stream(self, text: str):
        # Nicht genutzt – Ausgabe wird als Gesamtnachricht verarbeitet
        pass

    def print_empty_line(self):
        # In Gradio irrelevant
        pass

    def print_exit(self):
        # Optional: könnte verwendet werden für UI-Shutdown-Hinweise
        pass

    def respond(self, user_input, chat_history):
        """
        Callback-Funktion für Gradio, verarbeitet Benutzereingabe und gibt aktualisierte Nachrichtenliste zurück.
        Gradio erwartet hier eine Liste von {"role": ..., "content": ...} Dicts.
        """
        self.history.append({"role": "user", "content": user_input})

        reply = ""
        def collect_stream(token):
            nonlocal reply
            reply += token

        streaming_core.send_message_stream(
            messages=self.history,
            stream_url=self.stream_url,
            model_name=self.model_name,
            enable_logging=self.enable_logging,
            print_callback=collect_stream
        )

        self.history.append({"role": "assistant", "content": reply})
        return "", self.history  # Gradio erwartet diese Form bei type="messages"

    def launch(self):
        """
        Startet die Gradio Web-Oberfläche mit Chatbot im OpenAI-Format.
        """
        with gr.Blocks() as demo:
            gr.Markdown(f"## 🤖 Leah – Deine lokale KI-Assistentin (Modell: {self.model_name})")
            chatbot = gr.Chatbot(type="messages")  # nutzt OpenAI-kompatibles Format

            with gr.Row():
                txt = gr.Textbox(show_label=False, placeholder="Schreibe etwas...")

            txt.submit(self.respond, [txt, chatbot], [txt, chatbot])

        demo.launch()

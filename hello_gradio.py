# hello_gradio.py
import gradio as gr

def sag_hallo(name):
    return f"Hallo, {name}!"

demo = gr.Interface(fn=sag_hallo, inputs="text", outputs="text", title="Gradio Test")

demo.launch()
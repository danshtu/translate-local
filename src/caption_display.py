import tkinter as tk

class CaptionDisplay:
    def __init__(self, translator):
        self.translator = translator
        self.root = tk.Tk()
        self.root.title("Live Translation")
        self.root.geometry("1200x300")
        self.root.configure(bg="black")

        self.label = tk.Label(
            self.root,
            text="Listening...",
            font=("Arial", 32, "bold"),
            fg="white",
            bg="black",
            wraplength=1150,
            justify="center"
        )
        self.label.pack(expand=True, fill="both", padx=20, pady=20)

        self.root.after(100, self.update_text)

    def update_text(self):
        while not self.translator.text_queue.empty():
            result = self.translator.text_queue.get()
            self.label.config(text=result["translated"])

        self.root.after(100, self.update_text)

    def run(self):
        self.translator.start()
        self.root.mainloop()
        self.translator.stop()

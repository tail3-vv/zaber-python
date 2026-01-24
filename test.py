import tkinter as tk
import sys
import time

class App:
    def __init__(self, root):
        # Minimal tkinter app
        self.root = root
        self.root.title("MyApp")
        self.root.minsize(400, 300)

        # Add windows where we are going to write the std output. 
        self.console_text = tk.Text(self.root, state='disabled', height=10)
        self.console_text.pack(expand=True, fill='both')

        # We redirect sys.stdout -> TextRedirector
        self.redirect_sysstd()

        # We add a button to test our setup
        self.test_button = tk.Button(self.root, text="Test", command=self.test_text_redirection)
        self.test_button.pack(pady=10)

    def redirect_sysstd(self):
        # We specify that sys.stdout point to TextRedirector
        sys.stdout = TextRedirector(self.console_text, "stdout")
        sys.stderr = TextRedirector(self.console_text, "stderr")

    def test_text_redirection(self):
        for x in range(10):
            print(x+1)
            time.sleep(1)

class TextRedirector(object):
    def __init__(self, widget, tag):
        self.widget = widget
        self.tag = tag

    def write(self, text):
        self.widget.configure(state='normal') # Edit mode
        self.widget.insert(tk.END, text, (self.tag,)) # insert new text at the end of the widget
        self.widget.configure(state='disabled') # Static mode
        self.widget.see(tk.END) # Scroll down 
        self.widget.update_idletasks() # Update the console

    def flush(self):
        pass

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
import whisper
import torch
import tkinter as tk

from Tools import open_file, get_file_duration
import threading
import time
import os


class TranscriptionApp:
    def __init__(self):
        self.root = tk.Tk()
        self.label_file = tk.Label(self.root, text="No file loaded", anchor="center")
        self.label_model = tk.Label(self.root, text="No model loaded", anchor="center")

        self.filepath = ""
        self.size = 0
        self.model = None

        self._setup_window()

    def load_model(self):
        self.label_model["text"] = "Loading..."
        self.model = whisper.load_model("large-v2", device="cpu")
        self.model.encoder.to("cuda:0")
        self.model.decoder.to("cuda:1")

        self.model.decoder.register_forward_pre_hook(lambda _, inputs:
                                                     tuple([inputs[0].to("cuda:1"),
                                                            inputs[1].to("cuda:1")] + list(inputs[2:])))
        self.model.decoder.register_forward_hook(lambda _, inputs, outputs: outputs.to("cuda:0"))

        self.label_model["text"] = "loaded"

    def start_transcribing(self):
        work_thread = threading.Thread(target=self._transcribe_work)
        work_thread.start()

    def _transcribe_work(self):
        assert self.filepath
        audio_length = get_file_duration(self.filepath)
        print(f"Starting transcription... Recording duration: "
              f"{round(audio_length // 60)}:{round(audio_length % 60)} minutes.")
        estimate = audio_length * 1656 / (60*60)
        print(f"Estimated transcription time: {round(estimate // 60)}:{round(estimate % 60)} minutes.")
        start_time = time.time() # This is when the transcription process begins

        # This event is set when the transcription is complete
        done_event = threading.Event()

        # This function runs in a separate thread and prints the elapsed time every minute
        def print_time():
            while not done_event.is_set():
                elapsed_time = time.time() - start_time
                print(f"Elapsed time: {round(elapsed_time // 60)} minutes.")
                time.sleep(60)

        # Start the print_time function in a separate thread
        threading.Thread(target=print_time, daemon=True).start()

        result = self.model.transcribe(self.filepath)

        done_event.set()

        end_time = time.time()  # This is when the transcription process ends
        time_taken = end_time - start_time  # This will give the time taken in seconds
        print(f"Transcription took {round(time_taken // 60)} minutes, and {round(time_taken % 60)} seconds.")
        # transcription duration in seconds normalized to 1 hour recording time
        normalized_duration = time_taken/audio_length*3600
        print(f"Duration (normalized to 1h recording time): {round(normalized_duration // 60)} minutes, "
              f"and {round(normalized_duration % 60)} seconds")
        with open("Transcription/duration_statistics.txt", "a") as outFile:
            outFile.write(f"\n{normalized_duration}; "
                          f"{audio_length}; "
                          f"{os.path.basename(self.filepath)}; whole")

        with open("Transcription/output.txt", "w", encoding="utf-8") as outFile:
            outFile.write(result["text"])
        print("Transcription complete. See output.txt")

    # Define the loading function
    def load_file(self):
        self.filepath = open_file()
        self.label_file["text"] = os.path.basename(self.filepath)

    def _setup_window(self):
        self.label_file.pack()
        self.label_model.pack()

        button_load_file = tk.Button(self.root, text="Load file", command=self.load_file)
        button_load_file.pack()

        button_load_model = tk.Button(self.root, text="Load model", command=self.load_model)
        button_load_model.pack()

        button_transcribe = tk.Button(self.root, text="Transcribe", command=self.start_transcribing)
        button_transcribe.pack()

        self.root.mainloop()

        torch.Tensor.device = "cuda"


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    app = TranscriptionApp()

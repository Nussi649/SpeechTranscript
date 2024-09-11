import whisper
import torch
import tkinter as tk
from tkinter import ttk

import Tools
from Tools import open_file, process_file, knit_texts
from queue import Queue, Empty
import threading
import time
import os


class TranscriptionApp:
    def __init__(self):
        self.root = tk.Tk()
        self.label_file = tk.Label(self.root, text="No file loaded", anchor="center")
        self.label_model = tk.Label(self.root, text="No model loaded", anchor="center")
        self.progress_var = tk.IntVar()
        self.progress_var.set(0)
        self.progress_bar = ttk.Progressbar(self.root, length=200, mode='determinate',
                                            variable=self.progress_var, maximum=1)
        self.progress_text_var = tk.StringVar()
        self.progress_text_var.set("")
        self.progress_text_label = tk.Label(self.root, textvariable=self.progress_text_var)

        self.maximum_queue = Queue()
        self.progress_queue = Queue()
        self.filepath = ""
        self.audio_pieces = []
        self.size = 0
        self.model = None

        self._setup_window()

    def load_model(self):
        self.label_model["text"] = "Loading..."
        self.model = whisper.load_model("large-v3", device="cpu")
        self.model.encoder.to("cuda:0")
        self.model.decoder.to("cuda:1")

        self.model.decoder.register_forward_pre_hook(lambda _, inputs:
                                                     tuple([inputs[0].to("cuda:1"),
                                                            inputs[1].to("cuda:1")] + list(inputs[2:])))
        self.model.decoder.register_forward_hook(lambda _, inputs, outputs: outputs.to("cuda:0"))

        self.label_model["text"] = "Model loaded"

    def start_transcribing(self):
        self.maximum_queue = Queue()
        self.progress_queue = Queue()

        gui_update_thread = threading.Thread(target=self.update_gui)
        gui_update_thread.start()

        work_thread = threading.Thread(target=self._transcribe_work)
        work_thread.start()

    def _transcribe_work(self):
        assert self.audio_pieces
        assert self.filepath

        start_time = time.time()  # This is when the transcription process begins

        results = []
        total_audio_pieces = len(self.audio_pieces)
        self.progress_bar.pack()
        self.maximum_queue.put(total_audio_pieces)
        audio_length = Tools.get_file_duration(self.filepath)
        print(f"Starting transcription... Recording duration: "
              f"{round(audio_length // 60)}:{round(audio_length % 60):02d} minutes.")
        estimate = audio_length * 1341 / (60*60)
        print(f"Estimated transcription time: {round(estimate // 60)}:{round(estimate % 60):02d} minutes.")

        for idx, audio_path in enumerate(self.audio_pieces):
            audio = whisper.load_audio(audio_path)
            audio = whisper.pad_or_trim(audio)

            # make log-Mel spectrogram and move to the same device as the model
            mel = whisper.log_mel_spectrogram(audio, n_mels=128).to(self.model.device)

            if idx == 0:
                # detect the spoken language
                _, probs = self.model.detect_language(mel)
                print(f"Detected language: {max(probs, key=probs.get)}")

            # decode the audio
            options = whisper.DecodingOptions(fp16=False)
            result = whisper.decode(self.model, mel, options)
            results.append(result.text)
            elapsed_time = time.time() - start_time
            elapsed_minutes = int(elapsed_time // 60)
            elapsed_seconds = int(elapsed_time % 60)
            print(f"{idx + 1}/{total_audio_pieces} - t.e. {elapsed_minutes:02d}:{elapsed_seconds:02d}")

            self.progress_queue.put(idx + 1)  # Update the progress queue

        base_name = os.path.basename(self.filepath).split('.')[0]
        output_name = base_name + ".txt"
        output_name_long = base_name + "_long.txt"

        with open(f"Transcription/results/{output_name_long}", "w", encoding="utf-8") as outFile:
            for text in results:
                outFile.write(text)
                outFile.write('\n' * 2)
        print("finished writing long output.")

        end_time = time.time()  # This is when the transcription process ends

        time_taken = end_time - start_time  # This will give the time taken in seconds
        print(f"Transcription took {round(time_taken // 60)}:{round(time_taken % 60):02d} minutes.")
        # transcription duration in seconds normalized to 1 hour recording time
        normalized_duration = time_taken/total_audio_pieces*3600/Tools.PIECE_LENGTH
        print(f"Duration (normalized to 1h recording time): {round(normalized_duration // 60)}:{round(normalized_duration % 60):02d} minutes.")
        with open("Transcription/duration_statistics.txt", "a") as outFile:
            outFile.write(f"\n{normalized_duration}; "
                          f"{total_audio_pieces*Tools.PIECE_LENGTH}; "
                          f"{os.path.basename(self.filepath)}; chunked")
        print("")
        print("knitting results...")
        total_result = knit_texts(results)

        with open(f"Transcription/results/{output_name}", "w", encoding="utf-8") as outFile:
            outFile.write(total_result)
        print(f"Transcription complete. See results/{output_name}")

    def update_gui(self):
        maximum = -1
        progress = 0
        while True:
            try:
                maximum = self.maximum_queue.get_nowait()
                self.progress_bar.configure(maximum=maximum)
                print(f"Setting maximum to {maximum}")
                self.progress_var.set(0)
                self.progress_text_var.set(f'0/{self.progress_bar["maximum"]}')
                self.update_progress_label_position()
            except Empty:
                pass

            try:
                progress = self.progress_queue.get_nowait()
                self.progress_var.set(progress)
                self.progress_text_var.set(f'{progress}/{self.progress_bar["maximum"]}')
            except Empty:
                pass

            self.root.update_idletasks()
            time.sleep(0.01)
            if progress == maximum:
                break

    # Define the loading function
    def load_file(self):
        self.maximum_queue = Queue()
        self.progress_queue = Queue()
        self.label_file["text"] = "Loading..."

        self.filepath = open_file()

        def work():
            self.audio_pieces = process_file(self.filepath, self.progress_queue, self.maximum_queue)
            self.progress_bar.pack_forget()
            self.label_file["text"] = os.path.basename(self.filepath)

        self.progress_bar.pack()
        work_thread = threading.Thread(target=work)
        work_thread.start()

        gui_update_thread = threading.Thread(target=self.update_gui)
        gui_update_thread.start()

    def _setup_window(self):
        self.label_file.pack()
        self.label_model.pack()

        button_load_file = tk.Button(self.root, text="Load file", command=self.load_file)
        button_load_file.pack()

        button_load_model = tk.Button(self.root, text="Load model", command=self.load_model)
        button_load_model.pack()

        button_transcribe = tk.Button(self.root, text="Transcribe", command=self.start_transcribing)
        button_transcribe.pack()

        self.progress_bar.pack()
        self.progress_text_label.place(x=self.root.winfo_width() // 2, y=self.progress_bar.winfo_y(), anchor='center')
        self.root.after(100, self.update_progress_label_position)

        self.root.mainloop()

        torch.Tensor.device = "cuda"

    def update_progress_label_position(self):
        self.progress_text_label.place(x=self.root.winfo_width() // 2,
                                       y=self.progress_bar.winfo_y() + self.progress_bar.winfo_height() // 2,
                                       anchor='center')


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    app = TranscriptionApp()

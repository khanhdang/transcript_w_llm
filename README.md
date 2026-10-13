# transcript_w_llm

## Project brief

Design a program written in Python that runs on my PC and:

1. Takes audio input from the microphone.
2. Transcribes what I say into text.
3. Translates the transcription into a chosen language using a local LLM served by Ollama.
4. Displays the result on screen.

Presentation requirement: show the translated transcript as an overlay at the bottom of slides.

Technology choices: Python for the application and Ollama for local AI.

## Run the app

Use Python 3.9 or newer (3.11 or 3.12 recommended) with Tkinter installed.

On macOS, use modern Tk (8.6 or newer); Apple's command-line-tools Python uses obsolete Tk 8.5 and may show a blank window. Install a compatible runtime before creating the environment:

```sh
brew install python@3.12 python-tk@3.12
"$(brew --prefix python@3.12)/bin/python3.12" -m venv .venv
```

If an existing `.venv` was created with Apple's Python, close the app, rename that environment to `.venv-system-tk-backup`, and recreate `.venv` with the command above. Then install requirements as below. The app now stops with a clear message when launched with macOS Tk 8.5.

1. Install [Ollama](https://ollama.com/download), open it, and download a local model of your choice:

   ```sh
   ollama pull llama3.2:3b
   ```

   This is a small starting model; translation quality varies by model and language. You can select any installed local model in the app. Avoid cloud models if you want processing to stay on your PC.

2. From this folder, create an environment and install dependencies:

   ```sh
   python -m venv .venv
   ```

   Windows PowerShell:

   ```powershell
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   .venv\Scripts\python.exe app.py
   ```

   macOS / Linux (use `python3` instead of `python` above if needed):

   ```sh
   .venv/bin/python -m pip install -r requirements.txt
   .venv/bin/python app.py
   ```

3. Select your microphone, spoken language, target language, and installed Ollama model. Click **Start listening**, and allow microphone access if your operating system asks. **Stop** finishes pending audio. **Save text** exports the transcript and translation as UTF-8 text.

The default speech model is `base`, running on CPU. Its first use downloads weights from Hugging Face; subsequent use reads the cached model. Ollama also needs an initial model download. Once local models are downloaded, recognition and translation run locally. The application does not save microphone recordings.

## Behavior and troubleshooting

### Prepare slides and translations

Before listening, click **Load slides / context**. Supported files:

- `.pptx`: imports selectable slide text in presentation order. Images, charts, and speaker notes are not extracted.
- `.txt`: one slide per section, separated by a line containing `---`.
- `.md` / `.markdown`: Markdown slides separated by a line containing `---`. The first heading names each slide. Markdown text is retained as recognition/translation context; YAML front matter (such as Marp settings) is skipped, and separators inside fenced code blocks stay in their slide. Images are not extracted. See [examples/slides.md](examples/slides.md).
- `.json`: slide text, speaking notes, a bilingual glossary, and prepared translations. Start with [examples/presentation-context.json](examples/presentation-context.json).

In a JSON file, `target` identifies the glossary's translation language (use the same language name as **Translate to**). `glossary` maps source terms to preferred translated terms. Each slide can contain `title`, `text`, `notes`, and a `prepared` list. Each prepared entry needs `source` (what you plan to say), `translation`, and `target` (for example, `Japanese`). You can put exported slide text and your translations into this file together. Loading a file replaces the previous context; it does not merge files.

Select the current slide with the dropdown or **Previous / Next**, including while listening. Navigation is manual and does not control or follow PowerPoint. The selected slide supplies a bounded vocabulary/context hint to Whisper and reference material to Ollama. Glossary entries and prepared examples are used only for their specified target language. Prepared translations are displayed directly when the entire recognized caption matches a prepared source, ignoring punctuation, spacing, and case. Other speech is translated normally with the slide context. For best matching, make each prepared source a complete sentence or the complete group of sentences you expect in a caption.

Slide changes take effect at the next recognition chunk. Pending sentence fragments are translated with their original slide context before processing the new slide. Switch slides near a pause to avoid a recording chunk spanning two slides. Loading and removing context are disabled while listening. The context stays local and is sent only to the configured local Ollama service; it can improve terminology but recognition hints can also bias errors. Context is kept in memory for this session; load the file again after restarting.

### Subtitles over slides

Enable **Show slide subtitles** to display the latest translation in a borderless, always-on-top panel near the bottom of the screen. Use **Preview subtitles** to position it before speaking. Drag the panel to move it, including onto a second display; **Reset position** returns it to the main screen. Adjust **Text size** and **Opacity** in the main window. The panel shows white text on a dark background, without timestamps, and keeps the latest translation visible until another arrives or you click **Clear**.

Captions group one or several complete sentences into up to three lines. Text wraps between words (or characters for languages such as Japanese). The font shrinks down to 16 points when necessary to fit a sentence. Longer passages advance at sentence boundaries, with 6–20 seconds per page based on caption length. Exceptionally long sentences that cannot fit at the minimum size continue on another page; no text is truncated. A new translation replaces the previous pages.

Speech fragments without ending punctuation are held and joined with the next chunk before translation. A silent chunk, **Stop**, or three recognition chunks flushes unfinished text so it does not wait indefinitely. Sentence completeness depends on speech recognition punctuation, and this buffering can add latency.

Start listening, enable the overlay, then switch to your slides. The panel receives mouse clicks in its own area; click elsewhere on your slides to resume slide navigation after dragging it. Uncheck **Show slide subtitles** to hide it.

Use a windowed slide show or borderless presentation mode if full-screen slides cover the overlay. Native full-screen macOS Spaces and some exclusive full-screen applications can hide other app windows. For remote presentations, share the whole display containing both slides and subtitles; sharing only the slide application may exclude the overlay.

- The display updates in chunks, not word by word. The default recording interval is 5 seconds, plus recognition and translation time. Chunk boundaries can split sentences.
- Microphone capture continues during processing. Up to 30 seconds of recent audio is buffered. If processing cannot keep up, older audio is dropped and a status warning appears. Try `tiny` speech recognition or a smaller Ollama model.
- A quiet segment is filtered by faster-whisper's voice activity detector. Recognition can still make mistakes, particularly with noise.
- If Ollama is unreachable, open the Ollama app or run `ollama serve`. Use **Refresh microphones / models** after downloading a model.
- If Tkinter is missing, install a Python distribution that includes it. On Debian/Ubuntu install `python3-tk`; on Homebrew macOS install the matching `python-tk` package for your Python version.
- Linux may need the system PortAudio library (`libportaudio2` on Debian/Ubuntu). Windows and macOS sounddevice wheels normally include PortAudio.
- On macOS, enable microphone access for the terminal or Python app under System Settings → Privacy & Security → Microphone. On Windows, enable microphone access for desktop apps in Privacy settings.
- Stop can take time while a model is loading or a translation is in progress (HTTP requests have a 120-second timeout). Closing the window ends the application immediately.

## Development

`app.py` provides the Tkinter interface, microphone capture, and speech recognition. `backend.py` provides the local Ollama client and bounded audio buffer.

```sh
python -m unittest discover -s tests -v
```

Implementation references: [Ollama chat API](https://docs.ollama.com/api/chat), [faster-whisper](https://github.com/SYSTRAN/faster-whisper), and [sounddevice streams](https://python-sounddevice.readthedocs.io/en/latest/api/streams.html).

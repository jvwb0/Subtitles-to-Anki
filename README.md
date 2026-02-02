# Subtitles-to-Anki
Python program designed to create captions/subtitles with translations &amp; clickable words for quick grammar &amp; definition check while watching foreign videos. Click on a word you don't recognize, see its definition and even add it to your flashcard decks in Anki



29.1.2026//
current issue: 
main_fixed.py (the first milestone we achieved), recording audio,
save as wav. file, then transcribe the file-- it works
Whisper is able to decode chunks flawlessly.

BUT!!!

when we try to do this in a LIVE recording, stream of continuous chunks, we get absolutely no output.... 5 chunks.... thats nothing

so i turned on VSCODE GitCopilot and asked him to look through the files. 
with main_live_debug.py we realize that what i said before holds true. Static transcription works. 460 chunks. This debug class proved that, Transcription is blocking the audio capture loop. 

When liveTranscriber.tick() runs Whisper, it takes several seconds, and during that time the audio stream buffer fills up or gets lost.

The solution is to separate audio capture from transcription using threading.  SO, we begin threading to run both proccesses simultaneously. 


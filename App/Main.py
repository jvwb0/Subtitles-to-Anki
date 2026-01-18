import os
import sys
import argparse
import queue
import Sounddevice as sd
import numpy as np


'first we need to install Sounddevice to record audio from the screen,'
' then numPy to save audio data as an array,'
' and finally we will install Whisper to transcribe the audio into text'
'all this in a virtual environment to keep our dependencies organized'


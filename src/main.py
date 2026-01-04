from caption_display import CaptionDisplay
from live_translator import LiveTranslator


if __name__ == '__main__':
    translator = LiveTranslator()
    display = CaptionDisplay(translator)
    display.run()

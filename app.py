import json
import os
import re
import uuid
from datetime import datetime, date, timedelta

from kivy.app import App
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.graphics import Color as GColor, RoundedRectangle as GRR
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.spinner import Spinner
from kivy.uix.widget import Widget
from kivy.uix.floatlayout import FloatLayout
from kivy.properties import (
    ObjectProperty, StringProperty, ListProperty, DictProperty, NumericProperty
)
from kivy.metrics import dp, sp
from kivy.core.window import Window

# ─── Data File Path ───────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.expanduser("~"), ".memoir_journal")
DATA_FILE = os.path.join(DATA_DIR, "entries.json")
BOOKMARKS_FILE = os.path.join(DATA_DIR, "bookmarks.json")

MOOD_COLORS = {
    "Happy": (0.30, 0.69, 0.31, 1),
    "Calm": (0.25, 0.65, 0.85, 1),
    "Grateful": (0.61, 0.35, 0.71, 1),
    "Reflective": (0.38, 0.49, 0.55, 1),
    "Sad": (0.30, 0.39, 0.55, 1),
    "Anxious": (0.85, 0.49, 0.19, 1),
    "Angry": (0.80, 0.24, 0.24, 1),
    "Excited": (0.90, 0.68, 0.10, 1),
}


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def load_entries():
    ensure_data_dir()
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []


def save_entries(entries):
    ensure_data_dir()
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


def load_bookmarks():
    ensure_data_dir()
    if os.path.exists(BOOKMARKS_FILE):
        with open(BOOKMARKS_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []


def save_bookmarks(bookmarks):
    ensure_data_dir()
    with open(BOOKMARKS_FILE, "w", encoding="utf-8") as f:
        json.dump(bookmarks, f, indent=2, ensure_ascii=False)


# ─── Pure Python Text Checker Engine ──────────────────────────────────────────
class TextChecker:
    """Offline pure-Python spell and grammar checker."""
    def __init__(self):
        self._spell = None
        self._spell_checked = False

    @property
    def spell(self):
        if not self._spell_checked:
            self._spell_checked = True
            try:
                from spellchecker import SpellChecker
                self._spell = SpellChecker(distance=2)
            except Exception:
                pass
        return self._spell

    def check(self, text):
        if not text.strip():
            return []
        
        errors = []
        # 1. Custom Pure-Python Grammar Rules
        errors.extend(self._check_custom_grammar(text))
        # 2. Spelling Checker
        if self.spell:
            errors.extend(self._check_spelling(text))
        else:
            return None  # None means no checker library available at all
            
        errors.sort(key=lambda e: e['offset'])
        return errors

    def _check_custom_grammar(self, text):
        errors = []
        
        # Rule 1: Double words (e.g., "the the")
        for match in re.finditer(r'\b(\w+)\s+\1\b', text, re.IGNORECASE):
            word = match.group(1)
            start, end = match.span()
            errors.append({
                'context': self._get_context(text, start, end - start, word),
                'message': f"Repeated word: '{word}'",
                'replacements': [word],
                'offset': start,
                'length': end - start,
                'type': 'Grammar'
            })

        # Rule 2: Sentence capitalization
        sentences = re.split(r'(?<=[.!?])\s+', text)
        curr_idx = 0
        for sentence in sentences:
            if sentence:
                first_word_match = re.match(r'([a-z])(\w*)', sentence)
                if first_word_match:
                    start = curr_idx + first_word_match.start()
                    length = len(first_word_match.group(0))
                    word = first_word_match.group(0)
                    errors.append({
                        'context': self._get_context(text, start, length, word),
                        'message': "Sentence should start with a capital letter.",
                        'replacements': [word.capitalize()],
                        'offset': start,
                        'length': length,
                        'type': 'Grammar'
                    })
                curr_idx += len(sentence) + 1
            
        # Rule 3: Missing space after punctuation (e.g., "Hello,world")
        for match in re.finditer(r'[.,!?;:][A-Za-z]', text):
            start = match.start()
            word = text[start:start+2]
            errors.append({
                'context': self._get_context(text, start, 2, word),
                'message': "Missing space after punctuation.",
                'replacements': [f"{word[0]} {word[1]}"],
                'offset': start,
                'length': 2,
                'type': 'Grammar'
            })

        return errors

    def _check_spelling(self, text):
        errors = []
        for m in re.finditer(r'\b[a-zA-Z]+\b', text):
            word = m.group()
            if len(word) <= 1:
                continue
                
            if word.lower() not in self.spell:
                candidates = list(self.spell.candidates(word.lower()))[:3] if self.spell.candidates(word.lower()) else []
                if word[0].isupper():
                    candidates = [c.capitalize() for c in candidates]

                errors.append({
                    'context': self._get_context(text, m.start(), m.end() - m.start(), word),
                    'message': f"Possible spelling mistake: '{word}'",
                    'replacements': candidates,
                    'offset': m.start(),
                    'length': m.end() - m.start(),
                    'type': 'Spelling'
                })
        return errors

    def _get_context(self, text, offset, length, error_word):
        start = max(0, offset - 15)
        end = min(len(text), offset + length + 15)
        before = text[start:offset]
        after = text[offset + length:end]
        return f"{before}[b][color=ff5555]{error_word}[/color][/b]{after}"


# ─── Correction Popup ─────────────────────────────────────────────────────────
class CorrectionPopup(Popup):
    def __init__(self, errors, apply_callback, **kwargs):
        super().__init__(**kwargs)
        self.errors = errors
        self.current_idx = 0
        self.apply_callback = apply_callback

        self.layout = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(12))

        self.counter_label = Label(font_size=sp(14), color=(0.8, 0.8, 0.8, 1), 
                                   size_hint_y=None, height=dp(24))
        self.type_label = Label(font_size=sp(12), color=(0.61, 0.35, 0.71, 1), 
                                size_hint_y=None, height=dp(24), halign='left', valign='middle')
        self.type_label.bind(width=lambda i, v: setattr(i, 'text_size', (v, dp(24))))

        self.context_label = Label(font_size=sp(14), color=(0.9, 0.9, 0.9, 1), 
                                   size_hint_y=None, height=dp(60), halign='left', valign='middle', markup=True)
        self.context_label.bind(width=lambda i, v: setattr(i, 'text_size', (v, dp(60))))

        self.message_label = Label(font_size=sp(12), color=(0.7, 0.75, 0.8, 1), 
                                   size_hint_y=None, height=dp(50), halign='left', valign='top')
        self.message_label.bind(width=lambda i, v: setattr(i, 'text_size', (v, dp(50))))

        self.replacements_layout = BoxLayout(orientation='horizontal', size_hint_y=None, 
                                             height=dp(44), spacing=dp(8))

        self.nav_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(48), spacing=dp(8))
        self.prev_btn = Button(text="<< Prev", background_color=(0.25, 0.28, 0.33, 1), color=(0.8, 0.8, 0.8, 1))
        self.ignore_btn = Button(text="Ignore", background_color=(0.30, 0.33, 0.38, 1), color=(0.9, 0.9, 0.9, 1))
        self.next_btn = Button(text="Next >>", background_color=(0.25, 0.28, 0.33, 1), color=(0.8, 0.8, 0.8, 1))

        self.prev_btn.bind(on_release=self.prev_error)
        self.ignore_btn.bind(on_release=self.next_error)
        self.next_btn.bind(on_release=self.next_error)

        self.nav_layout.add_widget(self.prev_btn)
        self.nav_layout.add_widget(self.ignore_btn)
        self.nav_layout.add_widget(self.next_btn)

        self.layout.add_widget(self.counter_label)
        self.layout.add_widget(self.type_label)
        self.layout.add_widget(self.context_label)
        self.layout.add_widget(self.message_label)
        self.layout.add_widget(self.replacements_layout)
        self.layout.add_widget(self.nav_layout)

        self.content = self.layout
        self.title = "Spelling & Grammar"
        self.size_hint = (0.85, 0.6)
        self.background_color = (0.18, 0.20, 0.24, 0.98)
        self.separator_color = (0.61, 0.35, 0.71, 1)

        self.update_display()

    def update_display(self):
        if not self.errors:
            self.dismiss()
            App.get_running_app().show_simple_popup("Check Complete", "No errors found!")
            return

        err = self.errors[self.current_idx]
        self.counter_label.text = f"Error {self.current_idx + 1} of {len(self.errors)}"
        self.type_label.text = f"Type: {err.get('type', 'Unknown')}"
        self.context_label.text = f"... {err.get('context', '')} ..."
        self.message_label.text = err.get('message', '')

        self.replacements_layout.clear_widgets()
        for repl in err.get('replacements', []):
            btn = Button(text=repl, font_size=sp(13),
                         background_color=(0.20, 0.50, 0.80, 1), color=(1, 1, 1, 1))
            btn.bind(on_release=lambda inst, r=repl: self.apply_fix(r))
            self.replacements_layout.add_widget(btn)

        if not err.get('replacements'):
            lbl = Label(text="No suggestions", font_size=sp(12), color=(0.5, 0.5, 0.5, 1))
            self.replacements_layout.add_widget(lbl)

    def apply_fix(self, replacement):
        err = self.errors[self.current_idx]
        self.dismiss()
        self.apply_callback(err['offset'], err['length'], replacement)

    def next_error(self, *args):
        if self.current_idx < len(self.errors) - 1:
            self.current_idx += 1
        else:
            self.dismiss()
            return
        self.update_display()

    def prev_error(self, *args):
        if self.current_idx > 0:
            self.current_idx -= 1
        self.update_display()


# ─── KV Design Language ───────────────────────────────────────────────────────
KV = """
#:import dp kivy.metrics.dp
#:import sp kivy.metrics.sp

<CustomLabel@Label>:
    font_name: "Roboto"
    markup: True

<CustomButton@Button>:
    font_name: "Roboto"
    markup: True

<CustomTextInput@TextInput>:
    font_name: "Roboto"

# ─── Main Screen ──────────────────────────────────────────────────────────────
<MainScreen>:
    BoxLayout:
        orientation: "vertical"

        canvas.before:
            Color:
                rgba: (0.14, 0.16, 0.20, 1)
            Rectangle:
                pos: self.pos
                size: self.size

        BoxLayout:
            orientation: "horizontal"
            size_hint_y: None
            height: dp(60)
            padding: [dp(16), dp(8)]
            spacing: dp(8)

            CustomLabel:
                text: "[size=24][b]✦ Memoir[/b][/size]"
                markup: True
                font_size: sp(22)
                color: (0.95, 0.95, 0.95, 1)
                halign: "left"
                valign: "center"
                text_size: self.size
                size_hint_x: 0.4

            CustomTextInput:
                id: search_input
                hint_text: "Search entries..."
                size_hint_x: 0.45
                multiline: False
                font_size: sp(14)
                padding: [dp(12), dp(10), dp(12), dp(10)]
                background_color: (0.20, 0.22, 0.27, 1)
                foreground_color: (0.9, 0.9, 0.9, 1)
                cursor_color: (0.95, 0.95, 0.95, 1)
                on_text: root.search_entries(self.text)

            CustomButton:
                text: "⚙"
                size_hint_x: None
                width: dp(44)
                font_size: sp(20)
                background_color: (0.25, 0.28, 0.33, 1)
                color: (0.85, 0.85, 0.85, 1)
                on_release: root.show_settings()

        BoxLayout:
            orientation: "horizontal"
            size_hint_y: None
            height: dp(42)
            padding: [dp(12), dp(4)]
            spacing: dp(6)

            Spinner:
                id: mood_filter
                text: "All Moods"
                values: ["All Moods", "Happy", "Calm", "Grateful", "Reflective", "Sad", "Anxious", "Angry", "Excited"]
                size_hint_x: 0.35
                font_size: sp(13)
                background_color: (0.20, 0.22, 0.27, 1)
                color: (0.85, 0.85, 0.85, 1)
                on_text: root.filter_by_mood(self.text)

            Spinner:
                id: sort_filter
                text: "Newest First"
                values: ["Newest First", "Oldest First", "Title A-Z", "Title Z-A"]
                size_hint_x: 0.35
                font_size: sp(13)
                background_color: (0.20, 0.22, 0.27, 1)
                color: (0.85, 0.85, 0.85, 1)
                on_text: root.sort_entries(self.text)

            CustomButton:
                id: bookmark_btn
                text: "★ Bookmarks"
                size_hint_x: 0.3
                font_size: sp(12)
                background_color: (0.25, 0.28, 0.33, 1)
                color: (0.85, 0.85, 0.85, 1)
                on_release: root.toggle_bookmark_view()

        BoxLayout:
            orientation: "horizontal"
            size_hint_y: None
            height: dp(32)
            padding: [dp(16), dp(2)]
            CustomLabel:
                id: stats_label
                text: "0 entries"
                font_size: sp(11)
                color: (0.50, 0.55, 0.60, 1)
                halign: "left"
                valign: "center"
                text_size: self.size

        ScrollView:
            id: entries_scroll
            bar_width: dp(4)
            bar_color: (0.35, 0.38, 0.43, 1)
            scroll_type: ["bars", "content"]

            BoxLayout:
                id: entries_container
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height
                padding: [dp(12), dp(4)]
                spacing: dp(10)

    FloatLayout:
        CustomButton:
            text: "+"
            size_hint: None, None
            size: dp(56), dp(56)
            pos: root.width - dp(76), dp(16)
            font_size: sp(28)
            bold: True
            background_color: (0.30, 0.69, 0.31, 1)
            color: (1, 1, 1, 1)
            on_release:
                app.current_entry = None
                app.sm.current = "compose"


# ─── Compose Screen ───────────────────────────────────────────────────────────
<ComposeScreen>:
    BoxLayout:
        orientation: "vertical"

        canvas.before:
            Color:
                rgba: (0.14, 0.16, 0.20, 1)
            Rectangle:
                pos: self.pos
                size: self.size

        BoxLayout:
            orientation: "horizontal"
            size_hint_y: None
            height: dp(56)
            padding: [dp(8), dp(6)]
            spacing: dp(6)

            CustomButton:
                text: "← Back"
                size_hint_x: None
                width: dp(70)
                font_size: sp(13)
                background_color: (0.25, 0.28, 0.33, 1)
                color: (0.85, 0.85, 0.85, 1)
                on_release: root.go_back()

            CustomLabel:
                id: compose_title_label
                text: "[b]New Entry[/b]"
                markup: True
                font_size: sp(17)
                color: (0.95, 0.95, 0.95, 1)
                halign: "center"
                valign: "center"
                text_size: self.size

            CustomButton:
                text: "✓ Check"
                size_hint_x: None
                width: dp(75)
                font_size: sp(13)
                background_color: (0.55, 0.35, 0.71, 1)
                color: (1, 1, 1, 1)
                on_release: root.check_text()

            CustomButton:
                text: "Save"
                size_hint_x: None
                width: dp(70)
                font_size: sp(14)
                bold: True
                background_color: (0.30, 0.69, 0.31, 1)
                color: (1, 1, 1, 1)
                on_release: root.save_entry()

        ScrollView:
            bar_width: dp(4)

            BoxLayout:
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height
                padding: [dp(16), dp(12)]
                spacing: dp(12)

                CustomLabel:
                    text: "Title"
                    font_size: sp(12)
                    color: (0.55, 0.60, 0.65, 1)
                    halign: "left"
                    valign: "middle"
                    text_size: self.size
                    size_hint_y: None
                    height: dp(20)

                CustomTextInput:
                    id: title_input
                    hint_text: "Give your entry a title..."
                    multiline: False
                    font_size: sp(18)
                    bold: True
                    size_hint_y: None
                    height: dp(48)
                    padding: [dp(14), dp(12), dp(14), dp(8)]
                    background_color: (0.20, 0.22, 0.27, 1)
                    foreground_color: (0.95, 0.95, 0.95, 1)

                CustomLabel:
                    text: "Date"
                    font_size: sp(12)
                    color: (0.55, 0.60, 0.65, 1)
                    halign: "left"
                    valign: "middle"
                    text_size: self.size
                    size_hint_y: None
                    height: dp(20)

                CustomTextInput:
                    id: date_input
                    hint_text: "YYYY-MM-DD"
                    multiline: False
                    font_size: sp(15)
                    size_hint_y: None
                    height: dp(44)
                    padding: [dp(14), dp(10), dp(14), dp(8)]
                    background_color: (0.20, 0.22, 0.27, 1)
                    foreground_color: (0.95, 0.95, 0.95, 1)

                CustomLabel:
                    text: "How are you feeling?"
                    font_size: sp(12)
                    color: (0.55, 0.60, 0.65, 1)
                    halign: "left"
                    valign: "middle"
                    text_size: self.size
                    size_hint_y: None
                    height: dp(20)

                GridLayout:
                    id: mood_grid
                    cols: 4
                    size_hint_y: None
                    height: dp(110)
                    row_default_height: dp(36)
                    row_force_default: True
                    spacing: dp(6)
                    padding: [dp(2), dp(4)]

                CustomLabel:
                    text: "Tags (comma-separated)"
                    font_size: sp(12)
                    color: (0.55, 0.60, 0.65, 1)
                    halign: "left"
                    valign: "middle"
                    text_size: self.size
                    size_hint_y: None
                    height: dp(20)

                CustomTextInput:
                    id: tags_input
                    hint_text: "e.g. travel, family, reflection"
                    multiline: False
                    font_size: sp(14)
                    size_hint_y: None
                    height: dp(44)
                    padding: [dp(14), dp(10), dp(14), dp(8)]
                    background_color: (0.20, 0.22, 0.27, 1)
                    foreground_color: (0.95, 0.95, 0.95, 1)

                CustomLabel:
                    text: "Write your thoughts..."
                    font_size: sp(12)
                    color: (0.55, 0.60, 0.65, 1)
                    halign: "left"
                    valign: "middle"
                    text_size: self.size
                    size_hint_y: None
                    height: dp(20)

                CustomTextInput:
                    id: content_input
                    hint_text: "Dear diary..."
                    multiline: True
                    font_size: sp(15)
                    size_hint_y: None
                    height: dp(350)
                    padding: [dp(14), dp(14), dp(14), dp(14)]
                    background_color: (0.20, 0.22, 0.27, 1)
                    foreground_color: (0.95, 0.95, 0.95, 1)
                    cursor_color: (0.95, 0.95, 0.95, 1)
                    on_text: root.update_word_count()

                CustomLabel:
                    id: word_count_label
                    text: "0 words"
                    font_size: sp(11)
                    color: (0.45, 0.50, 0.55, 1)
                    halign: "right"
                    valign: "middle"
                    text_size: self.size
                    size_hint_y: None
                    height: dp(18)


# ─── View Screen ──────────────────────────────────────────────────────────────
<ViewScreen>:
    BoxLayout:
        orientation: "vertical"

        canvas.before:
            Color:
                rgba: (0.14, 0.16, 0.20, 1)
            Rectangle:
                pos: self.pos
                size: self.size

        BoxLayout:
            orientation: "horizontal"
            size_hint_y: None
            height: dp(56)
            padding: [dp(8), dp(6)]
            spacing: dp(8)

            CustomButton:
                text: "← Back"
                size_hint_x: None
                width: dp(80)
                font_size: sp(14)
                background_color: (0.25, 0.28, 0.33, 1)
                color: (0.85, 0.85, 0.85, 1)
                on_release: root.go_back()

            CustomLabel:
                text: ""
                size_hint_x: 0.3

            CustomButton:
                id: bookmark_view_btn
                text: "☆"
                size_hint_x: None
                width: dp(50)
                font_size: sp(22)
                background_color: (0.25, 0.28, 0.33, 1)
                color: (0.95, 0.85, 0.20, 1)
                on_release: root.toggle_bookmark()

            CustomButton:
                text: "Edit"
                size_hint_x: None
                width: dp(70)
                font_size: sp(13)
                background_color: (0.20, 0.50, 0.80, 1)
                color: (1, 1, 1, 1)
                on_release: root.edit_entry()

            CustomButton:
                text: "Delete"
                size_hint_x: None
                width: dp(80)
                font_size: sp(13)
                background_color: (0.75, 0.22, 0.17, 1)
                color: (1, 1, 1, 1)
                on_release: root.confirm_delete()

        ScrollView:
            bar_width: dp(4)

            BoxLayout:
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height
                padding: [dp(20), dp(16)]
                spacing: dp(10)

                BoxLayout:
                    orientation: "horizontal"
                    size_hint_y: None
                    height: dp(30)
                    CustomLabel:
                        id: view_mood
                        text: ""
                        font_size: sp(13)
                        bold: True
                        color: (0.61, 0.35, 0.71, 1)
                        halign: "left"
                        valign: "middle"
                        text_size: self.size
                    CustomLabel:
                        id: view_date
                        text: ""
                        font_size: sp(12)
                        color: (0.55, 0.60, 0.65, 1)
                        halign: "right"
                        valign: "middle"
                        text_size: self.size

                CustomLabel:
                    id: view_title
                    text: ""
                    font_size: sp(24)
                    bold: True
                    color: (0.95, 0.95, 0.95, 1)
                    halign: "left"
                    valign: "top"
                    text_size: self.width, None
                    size_hint_y: None
                    height: self.texture_size[1] + dp(8)

                CustomLabel:
                    id: view_tags
                    text: ""
                    font_size: sp(11)
                    color: (0.45, 0.55, 0.65, 1)
                    halign: "left"
                    valign: "middle"
                    text_size: self.size
                    size_hint_y: None
                    height: dp(22)

                Widget:
                    size_hint_y: None
                    height: dp(1)
                    canvas.before:
                        Color:
                            rgba: (0.30, 0.33, 0.38, 1)
                        Rectangle:
                            pos: self.pos
                            size: self.size

                CustomLabel:
                    id: view_content
                    text: ""
                    font_size: sp(15)
                    color: (0.85, 0.88, 0.90, 1)
                    halign: "left"
                    valign: "top"
                    text_size: self.width, None
                    size_hint_y: None
                    height: max(self.texture_size[1] + dp(16), dp(100))

                CustomLabel:
                    id: view_wordcount
                    text: ""
                    font_size: sp(11)
                    color: (0.45, 0.50, 0.55, 1)
                    halign: "right"
                    valign: "middle"
                    text_size: self.size
                    size_hint_y: None
                    height: dp(20)


# ─── Settings Screen ──────────────────────────────────────────────────────────
<SettingsScreen>:
    BoxLayout:
        orientation: "vertical"

        canvas.before:
            Color:
                rgba: (0.14, 0.16, 0.20, 1)
            Rectangle:
                pos: self.pos
                size: self.size

        BoxLayout:
            orientation: "horizontal"
            size_hint_y: None
            height: dp(56)
            padding: [dp(8), dp(6)]
            spacing: dp(8)

            CustomButton:
                text: "← Back"
                size_hint_x: None
                width: dp(80)
                font_size: sp(14)
                background_color: (0.25, 0.28, 0.33, 1)
                color: (0.85, 0.85, 0.85, 1)
                on_release:
                    app.sm.current = "main"

            CustomLabel:
                text: "[b]Settings[/b]"
                markup: True
                font_size: sp(18)
                color: (0.95, 0.95, 0.95, 1)
                halign: "center"
                valign: "center"
                text_size: self.size

            Widget:
                size_hint_x: None
                width: dp(80)

        ScrollView:
            BoxLayout:
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height
                padding: [dp(20), dp(16)]
                spacing: dp(14)

                CustomLabel:
                    text: "[b]Statistics[/b]"
                    markup: True
                    font_size: sp(16)
                    color: (0.85, 0.88, 0.90, 1)
                    size_hint_y: None
                    height: dp(30)

                CustomLabel:
                    id: settings_stats
                    text: ""
                    markup: True
                    font_size: sp(13)
                    color: (0.70, 0.73, 0.78, 1)
                    halign: "left"
                    valign: "top"
                    text_size: self.width, None
                    size_hint_y: None
                    height: dp(140)

                Widget:
                    size_hint_y: None
                    height: dp(1)
                    canvas.before:
                        Color:
                            rgba: (0.30, 0.33, 0.38, 1)
                        Rectangle:
                            pos: self.pos
                            size: self.size

                CustomLabel:
                    text: "[b]Data Management[/b]"
                    markup: True
                    font_size: sp(16)
                    color: (0.85, 0.88, 0.90, 1)
                    size_hint_y: None
                    height: dp(30)

                CustomButton:
                    text: "Export All Entries as JSON"
                    size_hint_y: None
                    height: dp(48)
                    font_size: sp(14)
                    background_color: (0.20, 0.50, 0.80, 1)
                    color: (1, 1, 1, 1)
                    on_release: root.export_json()

                CustomButton:
                    text: "Export All Entries as Text"
                    size_hint_y: None
                    height: dp(48)
                    font_size: sp(14)
                    background_color: (0.20, 0.50, 0.80, 1)
                    color: (1, 1, 1, 1)
                    on_release: root.export_text()

                CustomButton:
                    text: "Delete All Entries"
                    size_hint_y: None
                    height: dp(48)
                    font_size: sp(14)
                    background_color: (0.75, 0.22, 0.17, 1)
                    color: (1, 1, 1, 1)
                    on_release: root.confirm_delete_all()

                Widget:
                    size_hint_y: None
                    height: dp(40)

                CustomLabel:
                    text: "Memoir v1.1 — Your personal journal"
                    font_size: sp(11)
                    color: (0.40, 0.43, 0.48, 1)
                    halign: "center"
                    size_hint_y: None
                    height: dp(20)
"""


# ─── Screens ──────────────────────────────────────────────────────────────────

class MainScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.filtered_entries = []
        self.showing_bookmarks = False
        Clock.schedule_once(self._delayed_init)

    def _delayed_init(self, dt):
        self.refresh_entries()

    def refresh_entries(self):
        entries = load_entries()
        search_text = self.ids.search_input.text.strip().lower()
        mood_filter = self.ids.mood_filter.text
        sort_mode = self.ids.sort_filter.text

        if self.showing_bookmarks:
            bookmarks = load_bookmarks()
            entries = [e for e in entries if e.get("id") in bookmarks]

        if search_text:
            entries = [
                e for e in entries
                if search_text in e.get("title", "").lower()
                or search_text in e.get("content", "").lower()
                or search_text in e.get("tags", "").lower()
            ]

        if mood_filter and mood_filter != "All Moods":
            entries = [e for e in entries if e.get("mood") == mood_filter]

        if sort_mode == "Newest First":
            entries.sort(key=lambda e: e.get("date", ""), reverse=True)
        elif sort_mode == "Oldest First":
            entries.sort(key=lambda e: e.get("date", ""), reverse=False)
        elif sort_mode == "Title A-Z":
            entries.sort(key=lambda e: e.get("title", "").lower())
        elif sort_mode == "Title Z-A":
            entries.sort(key=lambda e: e.get("title", "").lower(), reverse=True)

        self.filtered_entries = entries
        self._render_entries()
        self._update_stats()

    def _render_entries(self):
        container = self.ids.entries_container
        container.clear_widgets()

        if not self.filtered_entries:
            lbl = Label(
                text="No entries yet.\\nTap + to start writing!"
                if not self.showing_bookmarks else "No bookmarked entries.",
                markup=True, font_size=sp(16), color=(0.50, 0.55, 0.60, 1),
                halign="center", size_hint_y=None, height=dp(200),
            )
            container.add_widget(lbl)
            return

        for entry in self.filtered_entries:
            card = self._build_entry_card(entry)
            container.add_widget(card)

    def _build_entry_card(self, entry):
        content_preview = entry.get("content", "").replace("\n", " ")[:120]
        mood = entry.get("mood", "")
        mood_color = MOOD_COLORS.get(mood, (0.45, 0.50, 0.55, 1))

        card = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(120),
                         padding=[dp(14), dp(10)], spacing=dp(4))

        def update_canvas(instance, _value):
            instance.canvas.before.clear()
            with instance.canvas.before:
                GColor(0.22, 0.24, 0.29, 1)
                GRR(pos=instance.pos, size=instance.size, radius=[dp(12)])
                GColor(*mood_color)
                GRR(pos=(instance.x, instance.y), size=(dp(5), instance.height),
                    radius=[dp(12), 0, 0, dp(12)])

        card.bind(pos=update_canvas, size=update_canvas)
        update_canvas(card, None)

        top_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(24))
        title_lbl = Label(text=entry.get("title", "Untitled"), font_size=sp(16), bold=True,
                          color=(0.95, 0.95, 0.95, 1), halign="left", valign="middle", size_hint_x=0.7)
        title_lbl.bind(width=lambda i, v: setattr(i, "text_size", (v, dp(24))))
        mood_lbl = Label(text=mood, font_size=sp(12), color=mood_color,
                         halign="right", valign="middle", size_hint_x=0.3)
        mood_lbl.bind(width=lambda i, v: setattr(i, "text_size", (v, dp(24))))
        top_row.add_widget(title_lbl)
        top_row.add_widget(mood_lbl)

        date_lbl = Label(text=entry.get("date", ""), font_size=sp(11), color=(0.55, 0.60, 0.65, 1),
                         halign="left", valign="middle", size_hint_y=None, height=dp(18))
        date_lbl.bind(width=lambda i, v: setattr(i, "text_size", (v, dp(18))))

        preview_lbl = Label(text=content_preview, font_size=sp(13), color=(0.75, 0.78, 0.82, 1),
                            halign="left", valign="top", size_hint_y=None, height=dp(50), ellipsis="...")
        preview_lbl.bind(width=lambda i, v: setattr(i, "text_size", (v, dp(50))))

        card.add_widget(top_row)
        card.add_widget(date_lbl)
        card.add_widget(preview_lbl)

        entry_id = entry.get("id")
        card.bind(on_touch_down=lambda inst, touch, eid=entry_id: self._on_card_touch(inst, touch, eid))
        return card

    def _on_card_touch(self, instance, touch, entry_id):
        if instance.collide_point(*touch.pos):
            App.get_running_app().current_entry = entry_id
            self.manager.current = "view"
            self.manager.get_screen("view").load_entry(entry_id)
            return True
        return False

    def _update_stats(self):
        all_entries = load_entries()
        total = len(all_entries)
        total_words = sum(e.get("word_count", len(e.get("content", "").split())) for e in all_entries)
        stats_text = f"{total} entries  ·  {total_words} words"
        if self.showing_bookmarks:
            stats_text = f"★ Bookmarks  ·  {len(self.filtered_entries)} shown"
        self.ids.stats_label.text = stats_text

    def search_entries(self, text): self.refresh_entries()
    def filter_by_mood(self, text): self.refresh_entries()
    def sort_entries(self, text): self.refresh_entries()

    def toggle_bookmark_view(self):
        self.showing_bookmarks = not self.showing_bookmarks
        btn = self.ids.bookmark_btn
        if self.showing_bookmarks:
            btn.text = "★ All Entries"
            btn.background_color = (0.55, 0.45, 0.15, 1)
        else:
            btn.text = "★ Bookmarks"
            btn.background_color = (0.25, 0.28, 0.33, 1)
        self.refresh_entries()

    def show_settings(self):
        self.manager.current = "settings"
        self.manager.get_screen("settings").update_stats()


class ComposeScreen(Screen):
    moods = ["Happy", "Calm", "Grateful", "Reflective", "Sad", "Anxious", "Angry", "Excited"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected_mood = ""
        self.editing_id = None
        self.text_checker = TextChecker()
        Clock.schedule_once(self._build_mood_buttons)

    def _build_mood_buttons(self, dt):
        grid = self.ids.mood_grid
        grid.clear_widgets()
        for mood in self.moods:
            color = MOOD_COLORS.get(mood, (0.5, 0.5, 0.5, 1))
            btn = ToggleButton(text=mood, font_size=sp(12), background_color=(0.20, 0.22, 0.27, 1),
                               color=color, group="mood")
            btn.bind(on_press=lambda inst, m=mood: self._select_mood(m))
            grid.add_widget(btn)

    def _select_mood(self, mood):
        self.selected_mood = mood

    def on_enter(self, *args):
        app = App.get_running_app()
        if app.current_entry:
            self.editing_id = app.current_entry
            self._load_for_edit(app.current_entry)
            self.ids.compose_title_label.text = "[b]Edit Entry[/b]"
        else:
            self.editing_id = None
            self.ids.title_input.text = ""
            self.ids.date_input.text = datetime.now().strftime("%Y-%m-%d")
            self.ids.tags_input.text = ""
            self.ids.content_input.text = ""
            self.selected_mood = ""
            self.ids.compose_title_label.text = "[b]New Entry[/b]"
            for child in self.ids.mood_grid.children:
                child.state = "normal"
        self.update_word_count()

    def _load_for_edit(self, entry_id):
        entries = load_entries()
        entry = next((e for e in entries if e.get("id") == entry_id), None)
        if entry:
            self.ids.title_input.text = entry.get("title", "")
            self.ids.date_input.text = entry.get("date", "")
            self.ids.tags_input.text = entry.get("tags", "")
            self.ids.content_input.text = entry.get("content", "")
            self.selected_mood = entry.get("mood", "")
            for child in self.ids.mood_grid.children:
                child.state = "down" if child.text == self.selected_mood else "normal"

    def update_word_count(self):
        content = self.ids.content_input.text
        words = len(content.split()) if content.strip() else 0
        self.ids.word_count_label.text = f"{words} words"

    def check_text(self):
        text = self.ids.content_input.text
        if not text.strip():
            App.get_running_app().show_simple_popup("Check", "Nothing to check.")
            return

        errors = self.text_checker.check(text)
        if errors is None:
            App.get_running_app().show_simple_popup(
                "Checker Not Found",
                "Please install the spell checker:\n\n"
                "pip install pyspellchecker"
            )
            return

        if not errors:
            App.get_running_app().show_simple_popup("Check Complete", "No errors found!")
            return

        popup = CorrectionPopup(errors, self.apply_correction)
        popup.open()

    def apply_correction(self, offset, length, replacement):
        content = self.ids.content_input.text
        new_text = content[:offset] + replacement + content[offset + length:]
        self.ids.content_input.text = new_text
        self.check_text()  # Recalculate offsets and re-check remaining errors

    def save_entry(self):
        title = self.ids.title_input.text.strip()
        date_str = self.ids.date_input.text.strip()
        content = self.ids.content_input.text.strip()
        tags = self.ids.tags_input.text.strip()

        if not title: title = "Untitled"
        if not date_str: date_str = datetime.now().strftime("%Y-%m-%d")
        if not content:
            self._show_popup("Warning", "Please write something before saving.")
            return

        entries = load_entries()

        if self.editing_id:
            for e in entries:
                if e.get("id") == self.editing_id:
                    e["title"] = title
                    e["date"] = date_str
                    e["mood"] = self.selected_mood
                    e["tags"] = tags
                    e["content"] = content
                    e["word_count"] = len(content.split())
                    e["updated_at"] = datetime.now().isoformat()
                    break
        else:
            new_entry = {
                "id": str(uuid.uuid4()), "title": title, "date": date_str,
                "mood": self.selected_mood, "tags": tags, "content": content,
                "word_count": len(content.split()),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
            entries.append(new_entry)
            App.get_running_app().current_entry = new_entry["id"]

        save_entries(entries)
        self._show_popup("Saved!", "Your entry has been saved.", go_back=True)

    def go_back(self):
        App.get_running_app().current_entry = None
        self.manager.current = "main"
        self.manager.get_screen("main").refresh_entries()

    def _show_popup(self, title, message, go_back=False):
        content = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(12))
        content.add_widget(Label(text=message, font_size=sp(15), color=(0.9, 0.9, 0.9, 1)))
        btn = Button(text="OK", size_hint_y=None, height=dp(44),
                     background_color=(0.30, 0.69, 0.31, 1), color=(1, 1, 1, 1))
        content.add_widget(btn)
        popup = Popup(title=title, content=content, size_hint=(0.7, 0.35),
                      background_color=(0.18, 0.20, 0.24, 0.98), separator_color=(0.30, 0.69, 0.31, 1))
        if go_back:
            btn.bind(on_release=lambda *a: (popup.dismiss(), self.go_back()))
        else:
            btn.bind(on_release=popup.dismiss)
        popup.open()


class ViewScreen(Screen):
    entry_data = DictProperty({})

    def load_entry(self, entry_id):
        entries = load_entries()
        entry = next((e for e in entries if e.get("id") == entry_id), None)
        if entry:
            self.entry_data = entry
            self.ids.view_title.text = entry.get("title", "Untitled")
            self.ids.view_date.text = entry.get("date", "")
            self.ids.view_mood.text = entry.get("mood", "")
            self.ids.view_content.text = entry.get("content", "")
            tags = entry.get("tags", "")
            self.ids.view_tags.text = f"Tags: {tags}" if tags else ""
            word_count = entry.get("word_count", len(entry.get("content", "").split()))
            self.ids.view_wordcount.text = f"{word_count} words"
            mood = entry.get("mood", "")
            self.ids.view_mood.color = MOOD_COLORS.get(mood, (0.7, 0.7, 0.7, 1))
            bookmarks = load_bookmarks()
            self.ids.bookmark_view_btn.text = "★" if entry_id in bookmarks else "☆"

    def toggle_bookmark(self):
        entry_id = self.entry_data.get("id")
        if not entry_id: return
        bookmarks = load_bookmarks()
        if entry_id in bookmarks:
            bookmarks.remove(entry_id)
            self.ids.bookmark_view_btn.text = "☆"
        else:
            bookmarks.append(entry_id)
            self.ids.bookmark_view_btn.text = "★"
        save_bookmarks(bookmarks)

    def edit_entry(self):
        App.get_running_app().current_entry = self.entry_data.get("id")
        self.manager.current = "compose"

    def confirm_delete(self):
        content = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(12))
        content.add_widget(Label(text="Are you sure you want to delete this entry?\nThis cannot be undone.",
                                 font_size=sp(14), color=(0.9, 0.9, 0.9, 1)))
        btn_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(10))
        cancel_btn = Button(text="Cancel", background_color=(0.30, 0.33, 0.38, 1), color=(0.9, 0.9, 0.9, 1))
        delete_btn = Button(text="Delete", background_color=(0.75, 0.22, 0.17, 1), color=(1, 1, 1, 1))
        btn_row.add_widget(cancel_btn)
        btn_row.add_widget(delete_btn)
        content.add_widget(btn_row)

        popup = Popup(title="Delete Entry", content=content, size_hint=(0.75, 0.35),
                      background_color=(0.18, 0.20, 0.24, 0.98), separator_color=(0.75, 0.22, 0.17, 1))
        cancel_btn.bind(on_release=popup.dismiss)
        delete_btn.bind(on_release=lambda *a: (popup.dismiss(), self._do_delete()))
        popup.open()

    def _do_delete(self):
        entry_id = self.entry_data.get("id")
        entries = load_entries()
        save_entries([e for e in entries if e.get("id") != entry_id])
        bookmarks = load_bookmarks()
        if entry_id in bookmarks:
            bookmarks.remove(entry_id)
            save_bookmarks(bookmarks)
        self.go_back()

    def go_back(self):
        App.get_running_app().current_entry = None
        self.manager.current = "main"
        self.manager.get_screen("main").refresh_entries()


class SettingsScreen(Screen):
    def update_stats(self):
        entries = load_entries()
        total = len(entries)
        total_words = sum(e.get("word_count", len(e.get("content", "").split())) for e in entries)

        mood_counts = {}
        for e in entries:
            m = e.get("mood", "None")
            mood_counts[m] = mood_counts.get(m, 0) + 1
        mood_lines = "\n".join(f"  {m}: {c}" for m, c in sorted(mood_counts.items(), key=lambda x: -x[1]))

        dates = sorted(set(e.get("date", "") for e in entries if e.get("date")))
        streak = 0
        if dates:
            try:
                today = date.today()
                d = today
                for i in range(365):
                    if d.isoformat() in dates:
                        streak += 1
                        d -= timedelta(days=1)
                    else:
                        if i == 0:
                            d -= timedelta(days=1)
                            continue
                        break
            except Exception:
                streak = 0

        text = (f"Total entries: {total}\n"
                f"Total words: {total_words}\n"
                f"Current streak: {streak} day{'s' if streak != 1 else ''}\n\n"
                f"Mood breakdown:\n{mood_lines if mood_lines else '  No entries yet'}")
        self.ids.settings_stats.text = text

    def export_json(self):
        entries = load_entries()
        if not entries:
            self._show_popup("Export", "No entries to export.")
            return
        export_path = os.path.join(os.path.expanduser("~"), "memoir_export.json")
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
        self._show_popup("Exported!", f"Saved to:\n{export_path}")

    def export_text(self):
        entries = load_entries()
        if not entries:
            self._show_popup("Export", "No entries to export.")
            return
        export_path = os.path.join(os.path.expanduser("~"), "memoir_export.txt")
        with open(export_path, "w", encoding="utf-8") as f:
            for i, e in enumerate(entries, 1):
                f.write(f"{'=' * 60}\nEntry #{i}\nTitle: {e.get('title', 'Untitled')}\n"
                        f"Date: {e.get('date', 'Unknown')}\nMood: {e.get('mood', 'None')}\n"
                        f"Tags: {e.get('tags', 'None')}\n{'─' * 60}\n{e.get('content', '')}\n\n")
        self._show_popup("Exported!", f"Saved to:\n{export_path}")

    def confirm_delete_all(self):
        content = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(12))
        content.add_widget(Label(text="[b]DELETE ALL ENTRIES?[/b]\n\nThis is permanent and cannot be undone!",
                                 markup=True, font_size=sp(14), color=(0.95, 0.6, 0.6, 1)))
        btn_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(10))
        cancel_btn = Button(text="Cancel", background_color=(0.30, 0.33, 0.38, 1), color=(0.9, 0.9, 0.9, 1))
        delete_btn = Button(text="DELETE ALL", background_color=(0.75, 0.22, 0.17, 1), color=(1, 1, 1, 1))
        btn_row.add_widget(cancel_btn)
        btn_row.add_widget(delete_btn)
        content.add_widget(btn_row)

        popup = Popup(title="Danger", content=content, size_hint=(0.75, 0.38),
                      background_color=(0.18, 0.20, 0.24, 0.98), separator_color=(0.75, 0.22, 0.17, 1))
        cancel_btn.bind(on_release=popup.dismiss)
        delete_btn.bind(on_release=lambda *a: (popup.dismiss(), self._do_delete_all()))
        popup.open()

    def _do_delete_all(self):
        save_entries([])
        save_bookmarks([])
        self.update_stats()

    def _show_popup(self, title, message):
        content = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(12))
        content.add_widget(Label(text=message, font_size=sp(14), color=(0.9, 0.9, 0.9, 1)))
        btn = Button(text="OK", size_hint_y=None, height=dp(44),
                     background_color=(0.30, 0.69, 0.31, 1), color=(1, 1, 1, 1))
        content.add_widget(btn)
        popup = Popup(title=title, content=content, size_hint=(0.7, 0.35),
                      background_color=(0.18, 0.20, 0.24, 0.98), separator_color=(0.30, 0.69, 0.31, 1))
        btn.bind(on_release=popup.dismiss)
        popup.open()


# ─── App ──────────────────────────────────────────────────────────────────────

class MemoirApp(App):
    current_entry = StringProperty(None, allownone=True)

    def build(self):
        Builder.load_string(KV)
        self.sm = ScreenManager(transition=FadeTransition(duration=0.25))
        self.sm.add_widget(MainScreen(name="main"))
        self.sm.add_widget(ComposeScreen(name="compose"))
        self.sm.add_widget(ViewScreen(name="view"))
        self.sm.add_widget(SettingsScreen(name="settings"))
        Window.clearcolor = (0.14, 0.16, 0.20, 1)
        return self.sm

    def show_simple_popup(self, title, message):
        content = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(12))
        content.add_widget(Label(text=message, font_size=sp(14), color=(0.9, 0.9, 0.9, 1)))
        btn = Button(text="OK", size_hint_y=None, height=dp(44),
                     background_color=(0.30, 0.69, 0.31, 1), color=(1, 1, 1, 1))
        content.add_widget(btn)
        popup = Popup(title=title, content=content, size_hint=(0.75, 0.4),
                      background_color=(0.18, 0.20, 0.24, 0.98), separator_color=(0.30, 0.69, 0.31, 1))
        btn.bind(on_release=popup.dismiss)
        popup.open()


if __name__ == "__main__":
    MemoirApp().run()
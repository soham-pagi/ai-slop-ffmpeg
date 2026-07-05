import os
import json
import argparse
import base64
import io
import gradio as gr
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="gradio")
warnings.filterwarnings("ignore", message=".*show_api.*")
from typing import Any
from PIL import Image
from src.video_generator import generate_video, run_gradio_generation

# Default paths matching project repository structure
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SCRIPT_PATH = os.path.join(BASE_DIR, "scripts", "How Ancient Humans Used Salt.txt")
DEFAULT_AUDIO_PATH = os.path.join(BASE_DIR, "audio", "How Ancient Humans Used Salt.wav")
DEFAULT_IMAGES_DIR = os.path.join(BASE_DIR, "images", "How Ancient Humans Used Salt")

# Load default script text if available
DEFAULT_SCRIPT_TEXT = ""
if os.path.exists(DEFAULT_SCRIPT_PATH):
    with open(DEFAULT_SCRIPT_PATH, "r", encoding="utf-8") as f:
        DEFAULT_SCRIPT_TEXT = f.read()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Dark Video Editor Theme CSS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EDITOR_CSS = """
/* ── Global dark editor palette ── */
.gradio-container {
    background: #1a1a2e !important;
    color: #e0e0e0 !important;
    font-family: 'Segoe UI', 'Inter', system-ui, sans-serif !important;
    max-width: 100% !important;
}
.dark .gradio-container { background: #1a1a2e !important; }

/* Panel backgrounds */
.gr-panel, .gr-box, .gr-form, .gr-accordion,
div[class*="block"], div[class*="panel"] {
    background: #16213e !important;
    border-color: #2a2a4a !important;
}

/* Input fields */
input, textarea, select, .gr-input, .gr-text-input {
    background: #0f0f23 !important;
    color: #e0e0e0 !important;
    border-color: #3a3a5c !important;
}

/* Buttons */
button.primary, button[class*="primary"] {
    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%) !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
    box-shadow: 0 2px 12px rgba(99, 102, 241, 0.3) !important;
    transition: all 0.2s ease !important;
}
button.primary:hover, button[class*="primary"]:hover {
    box-shadow: 0 4px 20px rgba(99, 102, 241, 0.5) !important;
    transform: translateY(-1px) !important;
}
button.secondary, button[class*="secondary"] {
    background: #2a2a4a !important;
    border: 1px solid #3a3a5c !important;
    color: #c0c0d0 !important;
    transition: all 0.2s ease !important;
}
button.secondary:hover, button[class*="secondary"]:hover {
    background: #3a3a5c !important;
    color: #fff !important;
}

/* Accordion styling */
.gr-accordion .label-wrap { color: #a0a0c0 !important; }

/* Labels */
label, .gr-label, span[data-testid="block-label"] {
    color: #8888aa !important;
    font-size: 12px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.5px !important;
}

/* Markdown headers */
h1, h2, h3, h4 { color: #e0e0ff !important; }
.markdown-text { color: #b0b0d0 !important; }

/* Header bar */
#editor-header {
    background: linear-gradient(90deg, #0f0f23 0%, #16213e 50%, #0f0f23 100%);
    border-bottom: 1px solid #2a2a4a;
    padding: 8px 16px;
    margin-bottom: 8px;
}

/* Video output */
video { border-radius: 6px !important; border: 1px solid #2a2a4a !important; }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #0f0f23; }
::-webkit-scrollbar-thumb { background: #3a3a5c; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #5a5a7c; }

/* Status bar styling */
#status-bar textarea {
    background: #0f0f23 !important;
    border: 1px solid #2a2a4a !important;
    color: #7cfc00 !important;
    font-family: 'Consolas', 'Fira Code', monospace !important;
    font-size: 12px !important;
}

/* Hide bridge textbox without removing it from DOM (visible=False destroys DOM in Svelte!) */
#timeline-json-bridge {
    display: none !important;
    height: 0 !important;
    width: 0 !important;
    overflow: hidden !important;
    position: absolute !important;
    pointer-events: none !important;
}
"""



# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Helper Functions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_image_thumbnail_b64(image_path, max_size=(80, 50)):
    """Return base64 thumbnail data URI for an image."""
    try:
        if not os.path.exists(image_path):
            return ""
        with Image.open(image_path) as img:
            img.thumbnail(max_size)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=75)
            b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
            return f"data:image/jpeg;base64,{b64}"
    except Exception:
        return ""


def build_timeline_html(rows):
    """
    Build the HTML for the drag-and-drop timeline table styled like a video editor.
    rows: list of dicts with keys: thumb_b64, filename, path, start, duration
    """
    if not rows:
        return """
        <div style="display:flex; align-items:center; justify-content:center; height:300px;
                    color:#555; font-size:14px; flex-direction:column; gap:12px;
                    background:#0d0d1a; border-radius:8px; border:1px dashed #2a2a4a;">
            <span style="font-size:40px; opacity:0.4;">🎞️</span>
            <span>Click <b style="color:#8b5cf6;">Populate Timeline</b> to load your clips</span>
        </div>
        """

    row_html = ""
    for i, r in enumerate(rows):
        thumb = r.get("thumb_b64", "")
        fname = r.get("filename", "")
        start = r.get("start", "0.0")
        dur = r.get("duration", "5.0")
        path = r.get("path", "")
        eff_val = r.get("effect", "Random / Global") or "Random / Global"
        trans_val = r.get("transition", "Random / Global") or "Random / Global"

        EFF_UI_MAP = {
            "zoom_in": "Slow Zoom In",
            "zoom_out": "Slow Zoom Out",
            "pan_right_zoom_in": "Pan Right + Zoom In",
            "pan_left_zoom_in": "Pan Left + Zoom In",
            "pan_up_zoom_in": "Pan Up + Zoom In",
            "pan_down_zoom_in": "Pan Down + Zoom In",
            "pan_right_zoom_out": "Pan Right + Zoom Out",
            "pan_left_zoom_out": "Pan Left + Zoom Out",
            "pan_up_right_zoom_in": "Diagonal Up-Right + Zoom",
            "pan_down_left_zoom_in": "Diagonal Down-Left + Zoom",
            "zoom_in_fast_slow": "Zoom In (Ease Out)",
            "zoom_out_slow_fast": "Zoom Out (Ease In)",
            "mirror_x": "Mirror Horizontal (MoviePy)",
            "mirror_y": "Mirror Vertical (MoviePy)",
            "black_and_white": "Black and White (MoviePy)",
            "invert_colors": "Invert Colors (MoviePy)",
            "none": "Static / No Effect",
            "No Effect": "Static / No Effect"
        }
        TRANS_UI_MAP = {
            "Cross-Dissolve (Hollywood Blend)": "Cross Dissolve",
            "Flash / Dip to White": "Dip to White",
            "Dip to Black": "Dip to Black",
            "Flash / Dip to Warm Gold": "Dip to Warm Gold",
            "Flash / Dip to Cool Cyan": "Dip to Cool Cyan",
            "Clean Cut (No Fade)": "Hard Cut (No Fade)",
            "No Transition": "Hard Cut (No Fade)",
            "Random Cinematic": "Random / Global"
        }
        eff_val = EFF_UI_MAP.get(eff_val, eff_val)
        trans_val = TRANS_UI_MAP.get(trans_val, trans_val)

        eff_options = [
            "Random / Global", "Slow Zoom In", "Slow Zoom Out", 
            "Pan Right + Zoom In", "Pan Left + Zoom In", "Pan Up + Zoom In", "Pan Down + Zoom In",
            "Pan Right + Zoom Out", "Pan Left + Zoom Out",
            "Diagonal Up-Right + Zoom", "Diagonal Down-Left + Zoom",
            "Zoom In (Ease Out)", "Zoom Out (Ease In)",
            "Mirror Horizontal (MoviePy)", "Mirror Vertical (MoviePy)",
            "Black and White (MoviePy)", "Invert Colors (MoviePy)",
            "Static / No Effect"
        ]
        trans_options = [
            "Random / Global", "Cross Dissolve", "Dip to White", "Dip to Black", 
            "Dip to Warm Gold", "Dip to Cool Cyan",
            "Slide In from Left", "Slide In from Right", "Slide In from Top", "Slide In from Bottom",
            "Cross Fade (MoviePy)", "Fade through Black (MoviePy)",
            "Hard Cut (No Fade)"
        ]

        eff_html = "".join([f'<option value="{opt}"{" selected" if opt == eff_val else ""}>{opt}</option>' for opt in eff_options])
        trans_html = "".join([f'<option value="{opt}"{" selected" if opt == trans_val else ""}>{opt}</option>' for opt in trans_options])

        thumb_img = (
            f'<img src="{thumb}" style="height:40px; width:64px; border-radius:3px; object-fit:cover; border:1px solid #3a3a5c;" />'
            if thumb else
            '<div style="height:40px; width:64px; background:#1a1a2e; border-radius:3px; display:flex; align-items:center; justify-content:center; border:1px solid #3a3a5c; font-size:16px;">🖼️</div>'
        )

        row_html += f"""
        <tr data-idx="{i}" data-path="{path}" data-filename="{fname}"
            class="tl-row">
          <td class="tl-cell tl-handle">⠿</td>
          <td class="tl-cell" style="text-align:center; width:50px;">{i + 1}</td>
          <td class="tl-cell" style="text-align:center; width:80px;">{thumb_img}</td>
          <td class="tl-cell tl-filename">{fname}</td>
          <td class="tl-cell" style="text-align:center; width:75px;">
            <input type="text" value="{start}" data-field="start" class="tl-input"
                   onchange="window.__startEdited && window.__startEdited()" />
          </td>
          <td class="tl-cell" style="text-align:center; width:75px;">
            <input type="text" value="{dur}" data-field="duration" class="tl-input"
                   onchange="window.__timelineChanged && window.__timelineChanged()" />
          </td>
          <td class="tl-cell" style="text-align:center; width:125px;">
            <select data-field="effect" class="tl-select" onchange="window.__timelineChanged && window.__timelineChanged()">{eff_html}</select>
          </td>
          <td class="tl-cell" style="text-align:center; width:145px;">
            <select data-field="transition" class="tl-select" onchange="window.__timelineChanged && window.__timelineChanged()">{trans_html}</select>
          </td>
        </tr>
        """

    total_dur = sum(float(r.get("duration", 0)) for r in rows if r.get("duration"))
    clip_count = len(rows)

    return f"""
    <style>
      #tl-container {{
        background: #0d0d1a;
        border-radius: 8px;
        border: 1px solid #2a2a4a;
        overflow: hidden;
      }}
      #tl-stats {{
        display: flex;
        gap: 24px;
        padding: 8px 16px;
        background: #111128;
        border-bottom: 1px solid #2a2a4a;
        font-size: 12px;
        color: #7777aa;
        font-family: 'Consolas', 'Fira Code', monospace;
      }}
      #tl-stats span {{ color: #a78bfa; font-weight: 600; }}
      #timeline-drag-table {{
        width: 100%;
        border-collapse: collapse;
      }}
      #timeline-drag-table thead tr {{
        background: #111128;
        border-bottom: 1px solid #2a2a4a;
      }}
      #timeline-drag-table th {{
        padding: 8px 10px;
        text-align: center;
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #6666aa;
        font-weight: 600;
        user-select: none;
      }}
      .tl-row {{
        cursor: grab;
        border-bottom: 1px solid #1a1a30;
        transition: background 0.15s ease;
      }}
      .tl-row:hover {{
        background: #1c1c3a !important;
      }}
      .tl-cell {{
        padding: 6px 8px;
        vertical-align: middle;
      }}
      .tl-handle {{
        width: 28px;
        text-align: center;
        color: #3a3a5c;
        font-size: 14px;
        cursor: grab;
        user-select: none;
        transition: color 0.15s;
      }}
      .tl-row:hover .tl-handle {{ color: #8b5cf6; }}
      .tl-filename {{
        font-size: 12px;
        font-family: 'Consolas', 'Fira Code', monospace;
        color: #c0c0e0;
        max-width: 200px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }}
      .tl-input {{
        width: 68px;
        padding: 4px 6px;
        border: 1px solid #2a2a4a;
        border-radius: 4px;
        background: #0f0f23;
        color: #e0e0ff;
        font-size: 12px;
        font-family: 'Consolas', 'Fira Code', monospace;
        text-align: center;
        outline: none;
        transition: border-color 0.2s, box-shadow 0.2s;
      }}
      .tl-input:focus {{
        border-color: #6366f1;
        box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2);
      }}
      .tl-select {{
        width: 100%;
        padding: 4px 6px;
        border: 1px solid #2a2a4a;
        border-radius: 4px;
        background: #0f0f23;
        color: #e0e0ff;
        font-size: 11px;
        font-family: 'Consolas', 'Fira Code', monospace;
        outline: none;
        transition: border-color 0.2s, box-shadow 0.2s;
        cursor: pointer;
      }}
      .tl-select:focus {{
        border-color: #8b5cf6;
        box-shadow: 0 0 0 2px rgba(139, 92, 246, 0.2);
      }}

      /* SortableJS ghost/chosen */
      .sortable-ghost {{
        background: #2a1a4a !important;
        opacity: 0.5;
      }}
      .sortable-chosen {{
        background: #1e1e3e !important;
        box-shadow: 0 0 12px rgba(139, 92, 246, 0.3);
      }}
    </style>

    <div id="tl-container">
      <div id="tl-stats">
        <div>CLIPS: <span>{clip_count}</span></div>
        <div>TOTAL: <span>{total_dur:.1f}s</span></div>
      </div>
      <div style="max-height:520px; overflow-y:auto;">
        <table id="timeline-drag-table">
          <thead>
            <tr>
              <th style="width:28px;"></th>
              <th style="width:50px;">#</th>
              <th style="width:80px;">Preview</th>
              <th style="text-align:left;">Filename</th>
              <th style="width:75px;">Start (s)</th>
              <th style="width:75px;">Duration (s)</th>
              <th style="width:125px;">Effect</th>
              <th style="width:145px;">Transition</th>
            </tr>
          </thead>
          <tbody id="timeline-tbody">
            {row_html}
          </tbody>
        </table>
      </div>
    </div>
    """


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SortableJS Initializer
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SORTABLE_INIT_JS = """
async () => {
    if (!window.Sortable) {
        await new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/Sortable.min.js';
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }

    function initSortable() {
        const tbody = document.getElementById('timeline-tbody');
        if (!tbody) { setTimeout(initSortable, 500); return; }
        if (tbody._sortableInstance) tbody._sortableInstance.destroy();
        tbody._sortableInstance = new Sortable(tbody, {
            animation: 200,
            handle: '.tl-handle',
            ghostClass: 'sortable-ghost',
            chosenClass: 'sortable-chosen',
            onEnd: function() { recalcAndSync(); }
        });
    }

    // Called on duration edit or drag-reorder: recalculates all start times
    window.__timelineChanged = function() { recalcAndSync(); };

    // Called on manual start edit: just syncs values to Gradio without overwriting starts
    window.__startEdited = function() { syncOnly(); };

    function pushToGradio(data) {
        const container = document.getElementById('timeline-json-bridge');
        if (!container) return;
        const el = container.querySelector('textarea, input');
        if (!el) return;
        
        const proto = el.tagName.toLowerCase() === 'textarea' 
            ? window.HTMLTextAreaElement.prototype 
            : window.HTMLInputElement.prototype;
        const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value').set;
        nativeSetter.call(el, JSON.stringify(data));
        el.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
        el.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
    }


    function updateStats(rows) {
        const statsEl = document.getElementById('tl-stats');
        if (!statsEl) return;
        let total = 0;
        rows.forEach(r => { total += parseFloat(r.duration) || 0; });
        statsEl.innerHTML =
            '<div>CLIPS: <span>' + rows.length + '</span></div>' +
            '<div>TOTAL: <span>' + total.toFixed(1) + 's</span></div>';
    }

    // Recalculate ascending starts from cumulative durations (reorder / duration edit)
    function recalcAndSync() {
        const tbody = document.getElementById('timeline-tbody');
        if (!tbody) return;
        const rows = tbody.querySelectorAll('tr');
        if (rows.length === 0) return;

        let cumulative = 0.0;
        const data = [];
        rows.forEach((tr, idx) => {
            const sInput = tr.querySelector('input[data-field="start"]');
            const dInput = tr.querySelector('input[data-field="duration"]');
            const eSelect = tr.querySelector('select[data-field="effect"]');
            const tSelect = tr.querySelector('select[data-field="transition"]');
            let dur = 5.0;
            if (dInput) {
                const p = parseFloat(dInput.value);
                if (!isNaN(p) && p > 0) dur = p;
            }

            // Auto-assign ascending start time
            if (sInput) sInput.value = cumulative.toFixed(2);

            // Update order number
            const cells = tr.querySelectorAll('td');
            if (cells.length >= 2) cells[1].textContent = idx + 1;

            const eff = eSelect ? eSelect.value : 'Random / Global';
            const trans = tSelect ? tSelect.value : 'Random / Global';

            data.push({
                path: tr.getAttribute('data-path') || '',
                filename: tr.getAttribute('data-filename') || '',
                start: cumulative.toFixed(2),
                duration: dur.toString(),
                effect: eff,
                transition: trans
            });
            cumulative += dur;
        });

        updateStats(data);
        pushToGradio(data);
    }

    // Sync current values as-is (manual start edit — don't overwrite user's timestamps)
    function syncOnly() {
        const tbody = document.getElementById('timeline-tbody');
        if (!tbody) return;
        const rows = tbody.querySelectorAll('tr');
        if (rows.length === 0) return;

        const data = [];
        rows.forEach((tr, idx) => {
            const sInput = tr.querySelector('input[data-field="start"]');
            const dInput = tr.querySelector('input[data-field="duration"]');
            const eSelect = tr.querySelector('select[data-field="effect"]');
            const tSelect = tr.querySelector('select[data-field="transition"]');

            const cells = tr.querySelectorAll('td');
            if (cells.length >= 2) cells[1].textContent = idx + 1;

            const eff = eSelect ? eSelect.value : 'Random / Global';
            const trans = tSelect ? tSelect.value : 'Random / Global';

            data.push({
                path: tr.getAttribute('data-path') || '',
                filename: tr.getAttribute('data-filename') || '',
                start: sInput ? sInput.value : '0.0',
                duration: dInput ? dInput.value : '5.0',
                effect: eff,
                transition: trans
            });
        });

        updateStats(data);
        pushToGradio(data);
    }

    const observer = new MutationObserver(() => {
        if (document.getElementById('timeline-tbody')) initSortable();
    });
    observer.observe(document.body, { childList: true, subtree: true });
    initSortable();
    recalcAndSync();
}
"""


READ_TIMELINE_JS = """
(old_val) => {
    const tbody = document.getElementById('timeline-tbody');
    if (!tbody) return old_val;
    const data = [];
    tbody.querySelectorAll('tr').forEach((tr) => {
        data.push({
            path: tr.getAttribute('data-path') || '',
            filename: tr.getAttribute('data-filename') || '',
            start: tr.querySelector('input[data-field="start"]')?.value || '0.0',
            duration: tr.querySelector('input[data-field="duration"]')?.value || '5.0',
            effect: tr.querySelector('select[data-field="effect"]')?.value || 'Random',
            transition: tr.querySelector('select[data-field="transition"]')?.value || 'Random'
        });
    });
    const new_val = JSON.stringify(data);
    const el = document.querySelector('#timeline-json-bridge textarea, #timeline-json-bridge input');
    if (el) {
        const proto = el.tagName.toLowerCase() === 'textarea' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
        const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value').set;
        if (nativeSetter) {
            nativeSetter.call(el, new_val);
            el.dispatchEvent(new Event('input', { bubbles: true }));
        }
    }
    return new_val;
}
"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#  Backend Functions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def populate_timeline(script_mode, script_file, script_text, audio_file, image_mode, images_folder, uploaded_images, mapping_mode):
    """Populate the timeline from uploaded images. Returns (html, json_data)."""
    try:
        from src.image_mapper import map_images_to_timestamps
        from src.timestamp_parser import parse_script, parse_script_text
        try:
            from moviepy import AudioFileClip
        except ImportError:
            from moviepy.editor import AudioFileClip  # type: ignore

        images_source = ""
        if image_mode == "Select Local Folder" and images_folder and os.path.exists(images_folder):
            images_source = images_folder
        elif image_mode == "Upload Image Files" and uploaded_images:
            images_source = [f.name if hasattr(f, "name") else f for f in uploaded_images]
        else:
            return build_timeline_html([]), "[]"

        audio_dur = 0.0
        if audio_file and os.path.exists(audio_file):
            try:
                clip = AudioFileClip(audio_file)
                audio_dur = clip.duration or 0.0
            except Exception:
                pass

        timestamps = None
        if script_mode == "Upload File" and script_file:
            path = script_file.name if hasattr(script_file, "name") else script_file
            _, timestamps = parse_script(path)
        elif script_mode == "Paste Text" and script_text and script_text.strip():
            _, timestamps = parse_script_text(script_text)

        mapped = map_images_to_timestamps(images_source, timestamps=timestamps, mode=mapping_mode, audio_duration=audio_dur)

        rows = []
        for mc in mapped:
            rows.append({
                "thumb_b64": get_image_thumbnail_b64(mc.image_path),
                "filename": os.path.basename(mc.image_path),
                "path": mc.image_path,
                "start": str(round(mc.start_time, 2)),
                "duration": str(round(mc.duration, 2)),
                "effect": getattr(mc, "effect", "Random / Global") or "Random / Global",
                "transition": getattr(mc, "transition", "Random / Global") or "Random / Global"
            })

        html = build_timeline_html(rows)
        json_data = json.dumps([{"path": r["path"], "filename": r["filename"], "start": r["start"], "duration": r["duration"], "effect": r.get("effect", "Random / Global"), "transition": r.get("transition", "Random / Global")} for r in rows])
        return html, json_data
    except Exception as e:
        error_html = f'<div style="color:#ff6b6b; padding:16px; background:#1a0a0a; border-radius:8px;">❌ {str(e)}</div>'
        return error_html, "[]"


def equalize_durations(audio_file, json_str):
    """Equalize durations across all rows based on audio length."""
    try:
        rows = json.loads(json_str) if json_str else []
        if not rows:
            return build_timeline_html([]), "[]"

        try:
            from moviepy import AudioFileClip
        except ImportError:
            from moviepy.editor import AudioFileClip  # type: ignore

        if audio_file and os.path.exists(audio_file):
            clip = AudioFileClip(audio_file)
            total_dur = clip.duration or 0.0
            per_dur = round(total_dur / len(rows), 2) if len(rows) > 0 else 5.0
        else:
            per_dur = 5.0

        new_rows = []
        curr_t = 0.0
        for r in rows:
            new_rows.append({
                "thumb_b64": get_image_thumbnail_b64(r.get("path", "")),
                "filename": r.get("filename", ""),
                "path": r.get("path", ""),
                "start": str(round(curr_t, 2)),
                "duration": str(per_dur),
                "effect": r.get("effect", "Random / Global"),
                "transition": r.get("transition", "Random / Global")
            })
            curr_t += per_dur

        html = build_timeline_html(new_rows)
        json_data = json.dumps([{"path": r["path"], "filename": r["filename"], "start": r["start"], "duration": r["duration"], "effect": r.get("effect", "Random / Global"), "transition": r.get("transition", "Random / Global")} for r in new_rows])
        return html, json_data
    except Exception:
        return build_timeline_html([]), "[]"


def sort_by_timestamp(json_str):
    """Sort rows by start timestamp."""
    try:
        rows = json.loads(json_str) if json_str else []
        if not rows:
            return build_timeline_html([]), "[]"

        from src.image_mapper import parse_time_str

        def get_ts(r):
            val = parse_time_str(r.get("start", "0"))
            return val if val is not None else 999999.0

        rows.sort(key=get_ts)

        new_rows = []
        for r in rows:
            new_rows.append({
                "thumb_b64": get_image_thumbnail_b64(r.get("path", "")),
                "filename": r.get("filename", ""),
                "path": r.get("path", ""),
                "start": r.get("start", "0.0"),
                "duration": r.get("duration", "5.0"),
                "effect": r.get("effect", "Random / Global"),
                "transition": r.get("transition", "Random / Global")
            })

        html = build_timeline_html(new_rows)
        json_data = json.dumps([{"path": r["path"], "filename": r["filename"], "start": r["start"], "duration": r["duration"], "effect": r.get("effect", "Random / Global"), "transition": r.get("transition", "Random / Global")} for r in new_rows])
        return html, json_data
    except Exception:
        return build_timeline_html([]), "[]"


def sync_timeline_bridge(val):
    return val


# Note: run_gradio_generation is imported from src.video_generator (native FFmpeg engine)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Build the Gradio Video Editor UI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

try:
    GRADIO_V6 = int(gr.__version__.split(".")[0]) >= 6
except Exception:
    GRADIO_V6 = False

blocks_kwargs: dict[str, Any] = {
    "title": "AI Video Maker",
}
if not GRADIO_V6:
    blocks_kwargs["theme"] = gr.themes.Default()  # type: ignore
    blocks_kwargs["css"] = EDITOR_CSS

with gr.Blocks(**blocks_kwargs) as demo:

    # ─── HEADER BAR ───
    gr.HTML("""
    <div id="editor-header" style="display:flex; align-items:center; justify-content:space-between;">
        <div style="display:flex; align-items:center; gap:10px;">
            <span style="font-size:22px;">🎬</span>
            <span style="font-size:16px; font-weight:700; color:#e0e0ff; letter-spacing:1px;">AI VIDEO MAKER</span>
            <span style="font-size:11px; color:#5555aa; padding-left:8px;">Ken Burns · GPU Accelerated</span>
        </div>
        <div style="font-size:11px; color:#4444aa; font-family:monospace;">v2.0</div>
    </div>
    """)

    with gr.Row(equal_height=False):

        # ━━━━ LEFT SIDEBAR: Media & Settings ━━━━
        with gr.Column(scale=3, min_width=300):

            # ── Media Bin ──
            with gr.Accordion("🖼️  MEDIA BIN", open=True):
                image_mode = gr.Radio(
                    choices=["Select Local Folder", "Upload Image Files"],
                    value="Select Local Folder",
                    label="Source",
                    container=False
                )
                images_folder = gr.Textbox(
                    label="Folder Path",
                    value=DEFAULT_IMAGES_DIR,
                    lines=1
                )
                uploaded_images = gr.File(
                    label="Drop images here",
                    file_count="multiple",
                    file_types=["image"],
                    visible=False
                )

                def toggle_image_mode(mode):
                    return {
                        images_folder: gr.update(visible=(mode == "Select Local Folder")),
                        uploaded_images: gr.update(visible=(mode == "Upload Image Files"))
                    }

                image_mode.change(toggle_image_mode, inputs=[image_mode], outputs=[images_folder, uploaded_images])

            # ── Audio Track ──
            with gr.Accordion("🔊  AUDIO TRACK", open=True):
                audio_file = gr.Audio(
                    label="Narration / Music",
                    type="filepath",
                    value=DEFAULT_AUDIO_PATH if os.path.exists(DEFAULT_AUDIO_PATH) else None
                )

            # ── Script ──
            with gr.Accordion("📝  SCRIPT & TIMESTAMPS", open=False):
                script_mode = gr.Radio(
                    choices=["Paste Text", "Upload File", "No Script"],
                    value="Paste Text",
                    label="Input Method",
                    container=False
                )
                script_text = gr.Textbox(
                    label="Script with [MM:SS] timestamps",
                    value=DEFAULT_SCRIPT_TEXT,
                    lines=6,
                    placeholder="[00:00 - 00:08]\nWelcome to my video..."
                )
                script_file = gr.File(
                    label="Upload .txt",
                    file_types=[".txt"],
                    visible=False
                )

                def toggle_script_mode(mode):
                    return {
                        script_text: gr.update(visible=(mode == "Paste Text")),
                        script_file: gr.update(visible=(mode == "Upload File"))
                    }

                script_mode.change(toggle_script_mode, inputs=[script_mode], outputs=[script_text, script_file])

            # ── Export Settings ──
            with gr.Accordion("⚙️  EXPORT SETTINGS", open=False):
                with gr.Row():
                    res_dropdown = gr.Dropdown(
                        choices=["1920x1080", "1280x720", "854x480", "1080x1920"],
                        value="1920x1080",
                        label="Resolution"
                    )
                    fps_dropdown = gr.Dropdown(
                        choices=[60, 30, 24],
                        value=60,
                        label="FPS"
                    )
                with gr.Row():
                    mapping_radio = gr.Radio(
                        choices=["index", "sequential"],
                        value="index",
                        label="Mapping",
                        container=False
                    )
                    transition_slider = gr.Slider(
                        minimum=0.0, maximum=1.0, value=0.4, step=0.1,
                        label="Transition (s)"
                    )
                with gr.Row():
                    transition_style_dropdown = gr.Dropdown(
                        choices=[
                            "Random", "Cross Dissolve", "Dip to White", "Dip to Black", 
                            "Dip to Warm Gold", "Dip to Cool Cyan",
                            "Slide In from Left", "Slide In from Right", "Slide In from Top", "Slide In from Bottom",
                            "Cross Fade (MoviePy)", "Fade through Black (MoviePy)",
                            "Hard Cut (No Fade)"
                        ],
                        value="Random",
                        label="Transition Style"
                    )
                    effect_strategy_dropdown = gr.Dropdown(
                        choices=["Random (No Consecutive Repeats)", "Cycle All (Ordered)", "Zoom Only", "Pan Only", "Dynamic Diagonals", "Static / No Effect"],
                        value="Random (No Consecutive Repeats)",
                        label="Effect Strategy"
                    )

        # ━━━━ RIGHT MAIN AREA: Timeline + Preview ━━━━
        with gr.Column(scale=7, min_width=500):

            # ── Timeline Toolbar ──
            gr.HTML("""
            <div style="display:flex; align-items:center; gap:8px; padding:6px 0; border-bottom:1px solid #2a2a4a; margin-bottom:8px;">
                <span style="font-size:13px; font-weight:700; color:#a78bfa; letter-spacing:1px; text-transform:uppercase;">
                    ✂️ Timeline
                </span>
                <span style="font-size:11px; color:#4a4a7a; margin-left:auto;">
                    Drag ⠿ to reorder (auto-recalcs starts) · Edit start/duration inline
                </span>
            </div>
            """)

            with gr.Row():
                populate_btn = gr.Button("🔄 Populate Timeline", variant="primary", size="sm")
                sort_btn = gr.Button("🔢 Sort by Time", variant="secondary", size="sm")
                equalize_btn = gr.Button("⏱️ Equalize", variant="secondary", size="sm")

            # ── Drag-and-Drop Timeline Table ──
            timeline_html = gr.HTML(
                value=build_timeline_html([]),
                label="Timeline"
            )

            # Hidden JSON bridge (kept in DOM via CSS so JS can manipulate it)
            timeline_json_bridge = gr.Textbox(
                value="[]",
                lines=2,
                elem_id="timeline-json-bridge"
            )


            # ── Export & Preview ──
            gr.HTML("""
            <div style="border-top:1px solid #2a2a4a; margin-top:12px; padding-top:10px;">
                <span style="font-size:13px; font-weight:700; color:#a78bfa; letter-spacing:1px; text-transform:uppercase;">
                    📺 Preview & Export
                </span>
            </div>
            """)

            with gr.Row():
                generate_btn = gr.Button("🎬  RENDER VIDEO", variant="primary", size="lg", scale=4)
                cancel_btn = gr.Button("❌  CANCEL RENDER", variant="stop", size="lg", scale=1)

            with gr.Row():
                with gr.Column(scale=7):
                    output_video = gr.Video(label="Preview")
                    output_file = gr.File(label="📥 Direct MP4 Download (Fast)", interactive=False)
                with gr.Column(scale=3):
                    output_status = gr.Textbox(
                        label="Console",
                        interactive=False,
                        lines=4,
                        elem_id="status-bar"
                    )

    # ─── Wire up event handlers ───

    populate_btn.click(
        fn=populate_timeline,
        inputs=[script_mode, script_file, script_text, audio_file, image_mode, images_folder, uploaded_images, mapping_radio],
        outputs=[timeline_html, timeline_json_bridge]
    )

    sort_btn.click(
        fn=sort_by_timestamp,
        inputs=[timeline_json_bridge],
        outputs=[timeline_html, timeline_json_bridge]
    )

    equalize_btn.click(
        fn=equalize_durations,
        inputs=[audio_file, timeline_json_bridge],
        outputs=[timeline_html, timeline_json_bridge]
    )

    gen_event = generate_btn.click(
        fn=sync_timeline_bridge,
        inputs=[timeline_json_bridge],
        outputs=[timeline_json_bridge],
        js=READ_TIMELINE_JS
    ).then(
        fn=run_gradio_generation,
        inputs=[
            script_mode, script_file, script_text, audio_file,
            image_mode, images_folder, uploaded_images,
            res_dropdown, fps_dropdown, transition_slider, mapping_radio,
            timeline_json_bridge, effect_strategy_dropdown, transition_style_dropdown
        ],
        outputs=[output_video, output_file, output_status]
    )

    def cancel_generation_fn():
        import subprocess
        try:
            subprocess.run(["pkill", "-9", "-f", "ffmpeg"], check=False)
        except Exception:
            pass
        return "🛑 Video generation cancelled by user! GPU memory freed and FFmpeg process terminated."

    cancel_btn.click(
        fn=cancel_generation_fn,
        inputs=None,
        outputs=[output_status],
        cancels=[gen_event]
    )

    # Initialize SortableJS on page load
    demo.load(None, None, None, js=SORTABLE_INIT_JS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Launch AI Video Maker")
    parser.add_argument("--share", action="store_true", help="Create a publicly shareable Gradio link (recommended on Kaggle!)")
    parser.add_argument("--port", type=int, default=7860, help="Port to run the server on")
    args = parser.parse_args()

    print("\n" + "="*60)
    print(" 🛠️  SYSTEM & GPU HARDWARE DIAGNOSTICS")
    print("="*60)
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            print(f"  [✓] PyTorch CUDA: AVAILABLE ({gpu_name}, {vram_gb:.2f} GB VRAM)")
            print(f"      -> Ken Burns animations will render 100% on GPU!")
        else:
            print("  [✗] PyTorch CUDA: NOT AVAILABLE (Using CPU / OpenCV fallback)")
    except Exception as e:
        print(f"  [✗] PyTorch CUDA: Check failed ({e})")

    try:
        import subprocess
        res = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True)
        if "h264_nvenc" in res.stdout:
            print("  [✓] FFmpeg NVENC: AVAILABLE (NVIDIA Hardware Encoding Enabled)")
            print("      -> Video export will stream directly to GPU NVENC!")
        else:
            print("  [✗] FFmpeg NVENC: NOT AVAILABLE (Using CPU libx264 fallback)")
    except Exception as e:
        print(f"  [✗] FFmpeg NVENC: Check failed ({e})")
    print("="*60 + "\n")

    print(f"\nLaunching AI Video Maker (Share={args.share}, Port={args.port}, Gradio v{gr.__version__})...")
    launch_kwargs: dict[str, Any] = {
        "share": args.share,
        "server_port": args.port,
    }
    if GRADIO_V6:
        launch_kwargs["theme"] = gr.themes.Default()  # type: ignore
        launch_kwargs["css"] = EDITOR_CSS

    demo.launch(**launch_kwargs)

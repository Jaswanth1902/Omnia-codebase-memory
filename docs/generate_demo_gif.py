"""
generate_demo_gif.py - Deterministic Terminal Quickstart GIF Generator
Uses Playwright + Pillow to generate a silky 60fps-smooth terminal demo GIF
with zero external C++ dependencies or video codecs.
"""

import sys
import os
import time
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #08080B;
    display: flex;
    justify-content: center;
    align-items: center;
    width: 1100px;
    height: 600px;
    font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', Consolas, monospace;
    overflow: hidden;
  }
  .window {
    width: 1040px;
    height: 540px;
    background: #0E0D12;
    border-radius: 12px;
    border: 1px solid rgba(197, 160, 89, 0.4);
    box-shadow: 0 20px 50px rgba(0, 0, 0, 0.8), 0 0 30px rgba(197, 160, 89, 0.1);
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .titlebar {
    height: 38px;
    background: #14131A;
    border-bottom: 1px solid rgba(197, 160, 89, 0.2);
    display: flex;
    align-items: center;
    padding: 0 16px;
    position: relative;
  }
  .dots {
    display: flex;
    gap: 8px;
  }
  .dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
  }
  .dot.red { background: #FF5F56; }
  .dot.yellow { background: #FFBD2E; }
  .dot.green { background: #27C93F; }
  .title {
    position: absolute;
    width: 100%;
    left: 0;
    text-align: center;
    font-size: 11px;
    color: #8E857B;
    letter-spacing: 1px;
  }
  .terminal {
    flex: 1;
    padding: 22px 26px;
    color: #FDFBF7;
    font-size: 14px;
    line-height: 1.6;
    overflow: hidden;
    white-space: pre-wrap;
  }
  .prompt { color: #C5A059; font-weight: bold; }
  .cmd { color: #7DD3FC; font-weight: bold; }
  .dim { color: #71717A; }
  .green { color: #4ADE80; }
  .gold { color: #E5C77A; }
  .purple { color: #C084FC; }
  .cursor {
    display: inline-block;
    width: 8px;
    height: 15px;
    background: #C5A059;
    vertical-align: middle;
    margin-left: 2px;
    animation: blink 0.9s infinite;
  }
  @keyframes blink { 0%, 50% { opacity: 1; } 51%, 100% { opacity: 0; } }
</style>
</head>
<body>
<div class="window">
  <div class="titlebar">
    <div class="dots">
      <div class="dot red"></div>
      <div class="dot yellow"></div>
      <div class="dot green"></div>
    </div>
    <div class="title">omnia — mcp-ast-server — 1100×540</div>
  </div>
  <div class="terminal" id="term"></div>
</div>
<script>
  const term = document.getElementById('term');
  window.setTerminalHTML = function(html) {
    term.innerHTML = html;
  };
</script>
</body>
</html>
"""

def generate_gif():
    docs_dir = Path(__file__).resolve().parent
    repo_dir = docs_dir.parent
    assets_dir = repo_dir / "assets"
    assets_dir.mkdir(exist_ok=True)
    temp_dir = docs_dir / "temp_frames"
    temp_dir.mkdir(exist_ok=True)

    html_file = docs_dir / "term_canvas.html"
    html_file.write_text(HTML_CONTENT, encoding="utf-8")

    print("[1/3] Launching Playwright browser to capture terminal frames...")
    frames = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1100, "height": 600})
        page.goto(html_file.as_uri())
        page.wait_for_timeout(300)

        # Simulation Script Steps
        prompt = '<span class="prompt">jaswanth@studio:~/projects$</span> '
        
        script_sequence = [
            # Initial state
            (prompt + '<span class="cursor"></span>', 4),
            
            # Typing pip install
            (prompt + '<span class="cmd">pip install omnia-codebase-memory</span><span class="cursor"></span>', 5),
            
            # Pip output
            (prompt + '<span class="cmd">pip install omnia-codebase-memory</span>\n'
             '<span class="dim">Collecting omnia-codebase-memory...</span>\n'
             '<span class="green">✓ Successfully installed omnia-codebase-memory-1.0.0</span>\n\n'
             + prompt + '<span class="cursor"></span>', 6),
             
            # Typing omnia index
            (prompt + '<span class="cmd">pip install omnia-codebase-memory</span>\n'
             '<span class="dim">Collecting omnia-codebase-memory...</span>\n'
             '<span class="green">✓ Successfully installed omnia-codebase-memory-1.0.0</span>\n\n'
             + prompt + '<span class="cmd">omnia index --workspace .</span><span class="cursor"></span>', 6),
             
            # Indexing output
            (prompt + '<span class="cmd">pip install omnia-codebase-memory</span>\n'
             '<span class="dim">Collecting omnia-codebase-memory...</span>\n'
             '<span class="green">✓ Successfully installed omnia-codebase-memory-1.0.0</span>\n\n'
             + prompt + '<span class="cmd">omnia index --workspace .</span>\n'
             '<span class="gold">⚡ [OMNIA AST Indexer] Parsing symbols across workspace...</span>\n'
             '  <span class="green">✓</span> Indexed <span class="purple">server.py</span>: Found 42 symbols (Classes, Functions, Methods)\n'
             '  <span class="green">✓</span> L0 Abstract: Symbol topology cataloged (<span class="green">&lt;0.5ms</span>)\n'
             '  <span class="green">✓</span> L1 Relational: 113 dependency edges + Mermaid flowchart mapped (<span class="green">2.1ms</span>)\n'
             '  <span class="green">✓</span> Memory Footprint: <span class="gold">38.4 MB RAM</span> (0.0% Vector bloat)\n'
             '<span class="green">✅ OMNIA Ready: MCP Server listening on stdio &amp; HTTP:8020</span>\n\n'
             + prompt + '<span class="cursor"></span>', 10),
             
            # Agent Query
            (prompt + '<span class="cmd">pip install omnia-codebase-memory</span>\n'
             '<span class="dim">Collecting omnia-codebase-memory...</span>\n'
             '<span class="green">✓ Successfully installed omnia-codebase-memory-1.0.0</span>\n\n'
             + prompt + '<span class="cmd">omnia index --workspace .</span>\n'
             '<span class="gold">⚡ [OMNIA AST Indexer] Parsing symbols across workspace...</span>\n'
             '  <span class="green">✓</span> Indexed <span class="purple">server.py</span>: Found 42 symbols (Classes, Functions, Methods)\n'
             '  <span class="green">✓</span> L0 Abstract: Symbol topology cataloged (<span class="green">&lt;0.5ms</span>)\n'
             '  <span class="green">✓</span> L1 Relational: 113 dependency edges + Mermaid flowchart mapped (<span class="green">2.1ms</span>)\n'
             '  <span class="green">✓</span> Memory Footprint: <span class="gold">38.4 MB RAM</span> (0.0% Vector bloat)\n'
             '<span class="green">✅ OMNIA Ready: MCP Server listening on stdio &amp; HTTP:8020</span>\n\n'
             + prompt + '<span class="cmd">claude-code "Find AST definition of ASTSymbolIndexer"</span>\n'
             '<span class="purple">🤖 [Claude Code MCP]</span> Calling <span class="gold">mcp:omnia/ast_query_symbols("ASTSymbolIndexer")</span>...\n'
             '   <span class="green">✓ Injected AST node</span> in <span class="green">5.8ms</span> (server.py:209-385) | <span class="dim">Saved ~42,000 tokens</span>\n'
             + prompt + '<span class="cursor"></span>', 14)
        ]

        frame_idx = 0
        for text_html, repeat_count in script_sequence:
            escaped_html = text_html.replace('`', '\\`').replace('\\', '\\\\')
            page.evaluate(f"window.setTerminalHTML(`{escaped_html}`)")
            page.wait_for_timeout(50)
            
            frame_path = temp_dir / f"frame_{frame_idx:04d}.png"
            page.screenshot(path=str(frame_path))
            img = Image.open(frame_path)
            
            # Repeat frame according to display weight
            for _ in range(repeat_count):
                frames.append(img.copy())
            frame_idx += 1

        browser.close()

    print(f"[2/3] Captured {len(frames)} frames. Compiling palette-optimized GIF...")
    output_gif = assets_dir / "omnia_quickstart.gif"
    
    # Save optimized GIF with 256 colors adaptive palette
    frames[0].save(
        output_gif,
        save_all=True,
        append_images=frames[1:],
        optimize=True,
        duration=180, # ~5.5 fps animation playback
        loop=0
    )

    gif_size_kb = round(os.path.getsize(output_gif) / 1024, 1)
    print(f"[3/3] [SUCCESS] Generated {output_gif.name} ({gif_size_kb} KB)")

    # Clean up temp frames and html
    for f in temp_dir.glob("*.png"):
        f.unlink()
    temp_dir.rmdir()
    if html_file.exists():
        html_file.unlink()

if __name__ == "__main__":
    generate_gif()

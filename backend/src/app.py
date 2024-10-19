from flask import Flask, request, jsonify, send_file, make_response
import datetime
from dataclasses import dataclass
from typing import List, Tuple
import statistics
from pathlib import Path
import tempfile
import os
import io

app = Flask(__name__)

@dataclass
class Subtitle:
    index: int
    start_time: datetime.timedelta
    end_time: datetime.timedelta
    text: List[str]
    
    @property
    def duration(self) -> float:
        return (self.end_time - self.start_time).total_seconds()
    
    @property
    def char_count(self) -> int:
        return sum(len(line) for line in self.text)
    
    @property
    def reading_speed(self) -> float:
        return self.char_count / self.duration if self.duration > 0 else 0
    
    @property
    def gap_to_next(self) -> float:
        return getattr(self, '_gap_to_next', 0)
    
    @gap_to_next.setter
    def gap_to_next(self, value: float):
        self._gap_to_next = value

def parse_time(time_str: str) -> datetime.timedelta:
    hours, minutes, seconds = time_str.replace(',', '.').split(':')
    seconds, milliseconds = seconds.split('.')
    return datetime.timedelta(
        hours=int(hours),
        minutes=int(minutes),
        seconds=int(seconds),
        milliseconds=int(milliseconds)
    )

def format_time(td: datetime.timedelta) -> str:
    total_seconds = td.total_seconds()
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    milliseconds = int((total_seconds * 1000) % 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

def parse_srt(content: str) -> List[Subtitle]:
    subtitles = []
    current_subtitle = None
    lines = content.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        
        if not line:
            if current_subtitle:
                subtitles.append(current_subtitle)
                current_subtitle = None
            continue
            
        if current_subtitle is None:
            try:
                current_subtitle = Subtitle(int(line), None, None, [])
            except ValueError:
                continue
        elif current_subtitle.start_time is None:
            try:
                time_range = line.split(' --> ')
                current_subtitle.start_time = parse_time(time_range[0])
                current_subtitle.end_time = parse_time(time_range[1])
            except (ValueError, IndexError):
                current_subtitle = None
        else:
            current_subtitle.text.append(line)
    
    if current_subtitle:
        subtitles.append(current_subtitle)
    
    return subtitles

def write_srt(subtitles: List[Subtitle]) -> str:
    """Write subtitles to string"""
    output = []
    for subtitle in subtitles:
        output.append(f"{subtitle.index}")
        output.append(f"{format_time(subtitle.start_time)} --> {format_time(subtitle.end_time)}")
        output.extend(subtitle.text)
        output.append("")  # Empty line between subtitles
    return "\n".join(output)

def adjust_subtitles(subtitles: List[Subtitle], offset_ms: int) -> List[Subtitle]:
    offset = datetime.timedelta(milliseconds=offset_ms)
    for subtitle in subtitles:
        subtitle.start_time += offset
        subtitle.end_time += offset
    return subtitles

def analyze_subtitles(subtitles: List[Subtitle]) -> dict:
    for i in range(len(subtitles) - 1):
        gap = (subtitles[i + 1].start_time - subtitles[i].end_time).total_seconds()
        subtitles[i].gap_to_next = gap
    
    reading_speeds = [sub.reading_speed for sub in subtitles]
    gaps = [sub.gap_to_next for sub in subtitles[:-1]]
    durations = [sub.duration for sub in subtitles]
    
    stats = {
        'avg_reading_speed': statistics.mean(reading_speeds),
        'std_reading_speed': statistics.stdev(reading_speeds),
        'avg_gap': statistics.mean(gaps),
        'std_gap': statistics.stdev(gaps),
        'avg_duration': statistics.mean(durations),
        'std_duration': statistics.stdev(durations),
        'total_subtitles': len(subtitles)
    }
    
    issues = []
    overlaps = []
    large_gaps = []
    fast_subs = []
    
    overlaps = [(i, sub) for i, sub in enumerate(subtitles[:-1]) 
                if sub.gap_to_next < 0]
    if overlaps:
        issues.append(f"Found {len(overlaps)} overlapping subtitles")
    
    large_gaps = [(i, sub) for i, sub in enumerate(subtitles[:-1])
                  if sub.gap_to_next > stats['avg_gap'] + 2 * stats['std_gap']]
    if large_gaps:
        issues.append(f"Found {len(large_gaps)} unusually large gaps")
    
    fast_subs = [(i, sub) for i, sub in enumerate(subtitles)
                 if sub.reading_speed > stats['avg_reading_speed'] + 2 * stats['std_reading_speed']]
    if fast_subs:
        issues.append(f"Found {len(fast_subs)} subtitles with very high reading speeds")

    first_sub_time = subtitles[0].start_time.total_seconds()
    if first_sub_time < 0.5:
        issues.append(f"First subtitle appears very early ({first_sub_time:.1f}s)")
    elif first_sub_time > 10:
        issues.append(f"First subtitle appears late ({first_sub_time:.1f}s)")
    
    return {
        'statistics': stats,
        'issues': issues,
        'overlaps': overlaps,
        'large_gaps': large_gaps,
        'fast_subs': fast_subs
    }

def suggest_fixes(analysis: dict) -> List[Tuple[str, int]]:
    fixes = []
    
    if analysis['overlaps']:
        max_overlap = min(sub.gap_to_next for _, sub in analysis['overlaps'])
        fixes.append(("fix_overlaps", int(-max_overlap * 1100)))
    
    for issue in analysis['issues']:
        if "First subtitle appears very early" in issue:
            fixes.append(("delay_start", 1000))
        elif "First subtitle appears late" in issue:
            fixes.append(("advance_start", -2000))
    
    return fixes

def apply_fixes(subtitles: List[Subtitle], analysis: dict) -> List[Subtitle]:
    fixes = suggest_fixes(analysis)
    adjusted_subtitles = subtitles
    
    for fix_type, value in fixes:
        adjusted_subtitles = adjust_subtitles(adjusted_subtitles, value)
    
    return adjusted_subtitles

@app.route('/api/analyze', methods=['POST'])
def analyze_srt():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.endswith('.srt'):
        return jsonify({'error': 'Invalid file format. Only .srt files are supported'}), 400
    
    try:
        content = file.read().decode('utf-8')
        subtitles = parse_srt(content)
        if not subtitles:
            return jsonify({'error': 'No valid subtitles found in file'}), 400
        
        analysis = analyze_subtitles(subtitles)
        return jsonify({
            'statistics': analysis['statistics'],
            'issues': analysis['issues']
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/fix', methods=['POST'])
def fix_srt():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.endswith('.srt'):
        return jsonify({'error': 'Invalid file format. Only .srt files are supported'}), 400
    
    try:
        content = file.read().decode('utf-8')
        subtitles = parse_srt(content)
        if not subtitles:
            return jsonify({'error': 'No valid subtitles found in file'}), 400
        
        analysis = analyze_subtitles(subtitles)
        fixed_subtitles = apply_fixes(subtitles, analysis)
        fixed_content = write_srt(fixed_subtitles)

        buffer = io.StringIO()
        buffer.write(fixed_content)
        buffer.seek(0)
        
        # Generate the output filename
        original_filename = os.path.splitext(file.filename)[0]
        output_filename = f"{original_filename}_fixed.srt"
        
        # Create response with file download
        response = make_response(fixed_content)
        response.headers['Content-Type'] = 'application/x-subrip'
        response.headers['Content-Disposition'] = f'attachment; filename={output_filename}'
        
        response.headers['X-Analysis-Total-Subtitles'] = str(analysis['statistics']['total_subtitles'])
        response.headers['X-Analysis-Issues'] = str(len(analysis['issues']))
        
        return response
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    return response

    
if __name__ == '__main__':
    app.run(debug=True, port=5000)

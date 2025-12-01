import subprocess
import shutil
import os
import tempfile
from typing import Optional, List, Tuple

class VideoExporter:
    @staticmethod
    def get_ffmpeg_path(custom_path: Optional[str] = None) -> Optional[str]:
        if custom_path and os.path.exists(custom_path) and os.access(custom_path, os.X_OK):
            return custom_path
        return shutil.which('ffmpeg')

    @staticmethod
    def ms_to_timestamp(ms: int) -> str:
        seconds = ms / 1000.0
        return f"{seconds:.3f}"

    @staticmethod
    def export_segment(ffmpeg_path: str, input_file: str, start_ms: int, end_ms: int, output_file: str) -> None:
        start = VideoExporter.ms_to_timestamp(start_ms)
        duration = VideoExporter.ms_to_timestamp(end_ms - start_ms)
        
        # Command: ffmpeg -ss start -i input -t duration -c:v libx264 -c:a aac output
        # Re-encoding for accuracy.
        cmd = [
            ffmpeg_path, '-y',
            '-ss', start,
            '-i', input_file,
            '-t', duration,
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'aac',
            output_file
        ]
        
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if process.returncode != 0:
            raise Exception(f"FFmpeg error: {process.stderr.decode()}")

    @staticmethod
    def export_merged_segments(ffmpeg_path: str, input_file: str, segments: List[Tuple[int, int]], output_file: str) -> None:
        # segments: list of (start_ms, end_ms)
        # Strategy: Create temp files for each clip, then concat.
        # Direct filter complex is cleaner but command length limits exist.
        # Concat demuxer is standard.
        
        temp_dir = tempfile.mkdtemp()
        file_list_path = os.path.join(temp_dir, 'files.txt')
        temp_files = []
        
        try:
            # 1. Extract each segment
            for i, (start, end) in enumerate(segments):
                seg_out = os.path.join(temp_dir, f'seg_{i:04d}.mp4')
                VideoExporter.export_segment(ffmpeg_path, input_file, start, end, seg_out)
                temp_files.append(seg_out)
            
            # 2. Create list file
            with open(file_list_path, 'w') as f:
                for tf in temp_files:
                    f.write(f"file '{tf}'\n")
            
            # 3. Concat
            # ffmpeg -f concat -safe 0 -i list.txt -c copy output
            cmd = [
                ffmpeg_path, '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', file_list_path,
                '-c', 'copy',
                output_file
            ]
            
            process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if process.returncode != 0:
                raise Exception(f"FFmpeg concat error: {process.stderr.decode()}")
                
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

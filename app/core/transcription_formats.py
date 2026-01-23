"""
Transcription Format Converters

Utilities to convert Whisper transcription results to various output formats:
- TXT: Plain text
- SRT: SubRip subtitles
- VTT: WebVTT subtitles
- JSON: Full transcription data with timestamps
- TSV: Tab-separated values with timestamps

Author: Whisper-Free Project
License: MIT
"""

import json
from typing import Dict, Any, List
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class TranscriptionFormatter:
    """Format Whisper transcription output to various file formats"""

    @staticmethod
    def to_txt(result: Dict[str, Any]) -> str:
        """
        Convert to plain text format.

        Args:
            result: Whisper transcription result

        Returns:
            Plain text string
        """
        text = result.get('text', '').strip()
        return text

    @staticmethod
    def to_srt(result: Dict[str, Any]) -> str:
        """
        Convert to SRT subtitle format.

        SRT format:
        1
        00:00:00,000 --> 00:00:04,000
        First subtitle text

        2
        00:00:04,000 --> 00:00:08,000
        Second subtitle text

        Args:
            result: Whisper transcription result with 'segments'

        Returns:
            SRT formatted string
        """
        segments = result.get('segments', [])

        if not segments:
            # Fallback: create single segment
            text = result.get('text', '').strip()
            if text:
                return "1\n00:00:00,000 --> 00:00:10,000\n" + text + "\n"
            return ""

        srt_lines = []
        for i, segment in enumerate(segments, 1):
            start = segment.get('start', 0)
            end = segment.get('end', 0)
            text = segment.get('text', '').strip()

            if not text:
                continue

            # Format timestamps
            start_time = TranscriptionFormatter._format_timestamp_srt(start)
            end_time = TranscriptionFormatter._format_timestamp_srt(end)

            # Add segment
            srt_lines.append(f"{i}")
            srt_lines.append(f"{start_time} --> {end_time}")
            srt_lines.append(text)
            srt_lines.append("")  # Blank line between segments

        return "\n".join(srt_lines)

    @staticmethod
    def to_vtt(result: Dict[str, Any]) -> str:
        """
        Convert to WebVTT subtitle format.

        VTT format:
        WEBVTT

        00:00:00.000 --> 00:00:04.000
        First subtitle text

        00:00:04.000 --> 00:00:08.000
        Second subtitle text

        Args:
            result: Whisper transcription result with 'segments'

        Returns:
            VTT formatted string
        """
        segments = result.get('segments', [])

        vtt_lines = ["WEBVTT", ""]

        if not segments:
            # Fallback: create single segment
            text = result.get('text', '').strip()
            if text:
                vtt_lines.append("00:00:00.000 --> 00:00:10.000")
                vtt_lines.append(text)
                vtt_lines.append("")
            return "\n".join(vtt_lines)

        for segment in segments:
            start = segment.get('start', 0)
            end = segment.get('end', 0)
            text = segment.get('text', '').strip()

            if not text:
                continue

            # Format timestamps
            start_time = TranscriptionFormatter._format_timestamp_vtt(start)
            end_time = TranscriptionFormatter._format_timestamp_vtt(end)

            # Add segment
            vtt_lines.append(f"{start_time} --> {end_time}")
            vtt_lines.append(text)
            vtt_lines.append("")  # Blank line between segments

        return "\n".join(vtt_lines)

    @staticmethod
    def to_json(result: Dict[str, Any]) -> str:
        """
        Convert to JSON format.

        Includes full transcription data with word-level timestamps.

        Args:
            result: Whisper transcription result

        Returns:
            JSON formatted string (pretty-printed)
        """
        # Create clean output dict
        output = {
            'text': result.get('text', ''),
            'language': result.get('language', 'unknown'),
            'segments': []
        }

        # Add segments if available
        for segment in result.get('segments', []):
            seg_data = {
                'id': segment.get('id'),
                'start': segment.get('start'),
                'end': segment.get('end'),
                'text': segment.get('text', '').strip(),
            }

            # Add words if available
            if 'words' in segment:
                seg_data['words'] = segment['words']

            output['segments'].append(seg_data)

        return json.dumps(output, indent=2, ensure_ascii=False)

    @staticmethod
    def to_tsv(result: Dict[str, Any]) -> str:
        """
        Convert to TSV (tab-separated values) format.

        Format:
        start\tend\ttext
        0.00\t4.50\tFirst segment text
        4.50\t8.30\tSecond segment text

        Args:
            result: Whisper transcription result with 'segments'

        Returns:
            TSV formatted string
        """
        segments = result.get('segments', [])

        tsv_lines = ["start\tend\ttext"]

        if not segments:
            # Fallback: create single row
            text = result.get('text', '').strip()
            if text:
                tsv_lines.append(f"0.00\t10.00\t{text}")
            return "\n".join(tsv_lines)

        for segment in segments:
            start = segment.get('start', 0)
            end = segment.get('end', 0)
            text = segment.get('text', '').strip()

            if not text:
                continue

            # Format timestamps as decimal seconds
            tsv_lines.append(f"{start:.2f}\t{end:.2f}\t{text}")

        return "\n".join(tsv_lines)

    @staticmethod
    def _format_timestamp_srt(seconds: float) -> str:
        """
        Format timestamp for SRT (HH:MM:SS,mmm).

        Args:
            seconds: Time in seconds

        Returns:
            Formatted timestamp (e.g., "00:01:23,456")
        """
        td = timedelta(seconds=seconds)
        hours = td.seconds // 3600
        minutes = (td.seconds % 3600) // 60
        secs = td.seconds % 60
        millis = td.microseconds // 1000

        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    @staticmethod
    def _format_timestamp_vtt(seconds: float) -> str:
        """
        Format timestamp for VTT (HH:MM:SS.mmm).

        Args:
            seconds: Time in seconds

        Returns:
            Formatted timestamp (e.g., "00:01:23.456")
        """
        td = timedelta(seconds=seconds)
        hours = td.seconds // 3600
        minutes = (td.seconds % 3600) // 60
        secs = td.seconds % 60
        millis = td.microseconds // 1000

        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


# Export formatters by extension
FORMAT_CONVERTERS = {
    'txt': TranscriptionFormatter.to_txt,
    'srt': TranscriptionFormatter.to_srt,
    'vtt': TranscriptionFormatter.to_vtt,
    'json': TranscriptionFormatter.to_json,
    'tsv': TranscriptionFormatter.to_tsv,
}


def convert_transcription(result: Dict[str, Any], format: str) -> str:
    """
    Convert Whisper transcription result to specified format.

    Args:
        result: Whisper transcription result dictionary
        format: Output format ('txt', 'srt', 'vtt', 'json', 'tsv')

    Returns:
        Formatted transcription string

    Raises:
        ValueError: If format is not supported
    """
    format = format.lower()

    if format not in FORMAT_CONVERTERS:
        raise ValueError(
            f"Unsupported format: {format}. "
            f"Supported: {', '.join(FORMAT_CONVERTERS.keys())}"
        )

    converter = FORMAT_CONVERTERS[format]
    try:
        return converter(result)
    except Exception as e:
        logger.error(f"Error converting to {format}: {e}", exc_info=True)
        raise


# Standalone test
if __name__ == "__main__":
    import sys

    # Test data
    test_result = {
        'text': 'Hello world. This is a test transcription.',
        'language': 'en',
        'segments': [
            {
                'id': 0,
                'start': 0.0,
                'end': 2.5,
                'text': 'Hello world.'
            },
            {
                'id': 1,
                'start': 2.5,
                'end': 5.0,
                'text': 'This is a test transcription.'
            }
        ]
    }

    print("=== TXT ===")
    print(TranscriptionFormatter.to_txt(test_result))
    print()

    print("=== SRT ===")
    print(TranscriptionFormatter.to_srt(test_result))
    print()

    print("=== VTT ===")
    print(TranscriptionFormatter.to_vtt(test_result))
    print()

    print("=== JSON ===")
    print(TranscriptionFormatter.to_json(test_result))
    print()

    print("=== TSV ===")
    print(TranscriptionFormatter.to_tsv(test_result))

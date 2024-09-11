import os
import math
import re
import subprocess
import moviepy.editor as mp
from pydub import AudioSegment
from tkinter import filedialog
from difflib import SequenceMatcher
from pydub.utils import mediainfo


# Define the length of each piece in seconds
PIECE_LENGTH = 15

# Define additional overlap between two successive parts in seconds
OVERLAP_SECONDS = 5

# define variable for piece_count. gets set at the beginning of splitting the video (even before checking whether
# splitting is necessary)
piece_count = 0

MINIMUM_MATCH_THRESHOLD = 0.5
MAXIMUM_OVERLAP_LENGTH = 200


# Function to extract the audio track from a video file
def extract_audio(input_filepath, output_filepath):
    # Check if the input file exists
    if not os.path.isfile(input_filepath):
        raise FileNotFoundError(f"No video file found at {input_filepath}")

    # Check if output already exists and skip if so
    if os.path.isfile(output_filepath):
        return

    # open the original video file as an audio segment
    video = AudioSegment.from_file(input_filepath)
    # save the audio track to a new file in MP3 format
    video.export(output_filepath, format='mp3')


# Function to split a video file into pieces -------- DEPRECATED
def split_video(input_filename, progress_queue, maximum_queue):
    # Use ffmpeg to split the input file into pieces of the specified length
    path_parts = os.path.split(input_filename)
    dir_name = os.path.join(path_parts[0], "temp", os.path.splitext(os.path.basename(input_filename))[0])
    length_in_seconds = mp.VideoFileClip(input_filename).duration
    global piece_count
    piece_count = math.floor(length_in_seconds / PIECE_LENGTH)
    if length_in_seconds - piece_count * PIECE_LENGTH > OVERLAP_SECONDS:
        piece_count += 1
    maximum_queue.put(piece_count*2)
    for i in range(0, piece_count):
        progress_queue.put(i)
        if os.path.exists(f"{dir_name}/video{i}.mp4"):
            continue
        starttime = i * PIECE_LENGTH
        duration = PIECE_LENGTH + OVERLAP_SECONDS
        start = convert_to_duration(starttime)
        dur = convert_to_duration(duration)

        subprocess.run(
            [
                "ffmpeg",
                "-i",
                input_filename,
                "-ss",
                start,
                "-t",
                dur,
                "-c:v",
                "copy",
                "-c:a",
                "copy",
                f"{dir_name}/video{i}.mp4",
            ]
        )


# Function to split an audio file into pieces
# PARAMS:
# input_filename (string): filepath to source audio file including complete filename
# progress_queue (Queue): queue to feed current progress values to GUI refresh function
# maximum_queue (Queue): queue to feed changes to maximum progress value to GUI refresh function
# RETURNS: List of filepaths (string) to all audio chunks required (including chunks that may already exist)
def split_audio(input_filepath, output_directory, progress_queue, maximum_queue):
    # get path of directory containing source file and in which to put the chunks
    dir_path = os.path.dirname(input_filepath)
    # check if source file exists and can be read
    try:
        length_in_seconds = mediainfo(input_filepath)["duration"]
    except KeyError:
        raise Exception(f"No audio file found at {input_filepath}")

    # gain access to global variable piece_count and set it according to lengths of source file and chunks
    global piece_count
    piece_count = math.floor(float(length_in_seconds) / PIECE_LENGTH)
    if float(length_in_seconds) - piece_count * PIECE_LENGTH > OVERLAP_SECONDS:
        piece_count += 1

    # set maximum progress value to piece_count + 1 (one extra for first extracting the audio from the whole video file)
    maximum_queue.put(piece_count + 1)

    # calculate duration of each chunk
    duration = PIECE_LENGTH + OVERLAP_SECONDS
    dur = convert_to_duration(duration)

    # create return list
    audio_chunks_paths = []

    # iterate through all piece_count chunks
    for i in range(piece_count):
        # update current progress value (remember, first step has already happened)
        progress_queue.put(i+1)
        # calculate filepath under which to write the chunk
        current_chunk_filepath = f"{output_directory}/audio{i}.mp3"
        # check if chunk has already been generated (possibly from previous run) and skip if that is the case
        if os.path.exists(current_chunk_filepath):
            audio_chunks_paths.append(current_chunk_filepath)
            continue

        # calculate start time of chunk and convert to HH:MM:SS format
        start_time = i * PIECE_LENGTH
        start = convert_to_duration(start_time)

        # Use ffmpeg to split the input file into pieces of the specified length
        subprocess.run(
            [
                "ffmpeg",
                "-i",
                input_filepath,
                "-ss",
                str(start),
                "-t",
                str(dur),
                "-c:a",
                "libmp3lame",
                current_chunk_filepath,
            ]
        )
        audio_chunks_paths.append(current_chunk_filepath)
    return audio_chunks_paths


def open_file():
    fp = filedialog.askopenfilename(filetypes=[("Audio/Video files", "*.mp4 *.m4a *.mp3")])
    path_parts = os.path.split(fp)
    new_dir = os.path.join(path_parts[0], "temp", os.path.splitext(os.path.basename(fp))[0])
    if not os.path.exists(new_dir):
        os.mkdir(new_dir)
    return fp


# Function to process a mp4/mp3/m4a file into overlapping chunks of its audio track.
# Within the source file's directory it creates a new subdirectory with the same name as the source file (w/o filetype).
# Within that subdirectory it stores the source file's audio track under that name (.mp3 instead of .mp4) if necessary.
# Within that subdirectory it also stores all the chunks named audio{i}.mp3
# It catches no Exceptions but the functions called may raise some. Need to be handled above!
# PARAMS:
# file_path (string): file path to the source mp4/mp3/m4a file
# RETURNS: List of filepaths (string) to all audio chunks required (including chunks that may already exist)
def process_file(file_path, progress_queue, maximum_queue):
    file_type = file_path.split(".")[-1]
    # calculate path to new temporary subdirectory used for storing all intermediate files
    path_parts = os.path.split(file_path)
    new_dir = os.path.join(path_parts[0], "temp", os.path.splitext(os.path.basename(file_path))[0])
    # calculate filepath of source audio in full length
    audio_track_full = os.path.join(new_dir, os.path.basename(file_path).split(".")[0] + ".mp3")
    if file_type == "mp3" or file_type == "m4a":
        audio_track_full = file_path

    # calculate number of pieces from length of video file first
    length_in_seconds = get_file_duration(file_path)
    global piece_count
    piece_count = math.floor(length_in_seconds / PIECE_LENGTH)
    if length_in_seconds - piece_count * PIECE_LENGTH > OVERLAP_SECONDS:
        piece_count += 1

    work_required = False
    chunk_filepaths = []
    # check if files are already existing
    if file_type == "mp4" and not os.path.exists(audio_track_full):
        # extract audio track from source video file and store it in dedicated directory
        extract_audio(file_path, audio_track_full)
    for i in range(piece_count):
        current_chunk_filepath = f"{new_dir}/audio{i}.mp3"
        if not os.path.exists(current_chunk_filepath):
            work_required = True
        else:
            chunk_filepaths.append(current_chunk_filepath)

    # check if work is required:
    if work_required:
        # set progress bar
        maximum_queue.put(piece_count + 1)
        progress_queue.put(0)
        # split full audio into chunks and return list of created filepaths
        return split_audio(audio_track_full, new_dir, progress_queue, maximum_queue)
    else:
        # just return list of chunk filepaths
        return chunk_filepaths


def get_file_duration(file_path):
    file_type = file_path.split(".")[-1]
    
    # For MP4 files, use ffprobe to get file info
    if file_type == "mp4":
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 
               'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', 
               file_path]
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            duration = float(output)
            return duration
        except subprocess.CalledProcessError as e:
            print(f"Error occurred: {e.output}")
            return None
    # Handling for MP3 and M4A files
    elif file_type == "mp3" or file_type == "m4a":
        from pydub import AudioSegment
        audio = AudioSegment.from_file(file_path, format=file_type)
        return audio.duration_seconds
    else:
        return None


def get_space_positions(text):
    return [i for i, char in enumerate(text) if char == ' ']


def get_overlap_start(primary, secondary, adjust_backwards=True, max_window_size=30):
    def fitness_function(character_size, match_ratio):
        return character_size * match_ratio ** 3

    # Check if the texts are not empty or just jibberish
    if not primary.strip() or not secondary.strip() or not re.search(r'\w', primary) or not re.search(r'\w', secondary):
        print("Alert: One or both of the texts are empty, contain only whitespace, or do not contain any words!")
        return -1, -1, -1

    # Get space positions for later adjustment
    spaces = get_space_positions(primary)

    # Initialize the sequence matcher
    seq_matcher = SequenceMatcher()

    # Store the results for each window size
    results = []

    # Iterate over window sizes
    for window_size in range(1, max_window_size + 1):
        # if the window size counted in words is already longer than primary, don't bother increasing it
        if window_size > len(spaces):
            break
        # calculate character count of last 'window_size_words' words in primary
        # if there are as many words in primary as 'window_size_words' then set window length to full length of primary
        window_size_chars = len(primary) - spaces[-window_size]

        # Set the sequences to match
        seq_matcher.set_seqs(primary[-window_size_chars:], secondary[:window_size_chars])

        # Compute the ratio
        ratio = seq_matcher.ratio()

        # Store the window size, start position, and ratio
        results.append((window_size, len(primary) - window_size_chars, ratio))

    # catch case where nothing was said during chunk -> no text -> zero iterations over window sizes
    if not results:
        return 0, 0, 0

    # Compute fitness values and find the maximum
    fitness_values = [fitness_function(len(primary) - start, ratio) for window_size, start, ratio in results]
    max_fitness_index = fitness_values.index(max(fitness_values))

    # Get the start position with the maximum fitness value
    start = results[max_fitness_index][1]

    # Catch case in which there is no overlap - avoid finding false positives
    if results[max_fitness_index][2] < MINIMUM_MATCH_THRESHOLD:
        return len(primary), len(primary), 0

    # Find the position of the nearest space that is less than or equal to the start position
    adjusted_start = 0

    # check for cases where search for adjusted start is futile:
    # - there are no spaces
    # - the first space appears only after the identified start point (for both directions)
    if not spaces or (spaces[0] > start if adjust_backwards else spaces[-1] < start):
        return 0, start, fitness_values[max_fitness_index]
    # otherwise try pushing the start back to the next space before the identified start point
    try:
        adjusted_start = max(space for space in spaces if space <= start) if adjust_backwards else \
            min(space for space in spaces if space >= start)
    except ValueError as e:
        # this should not be able to happen
        print(f"Starting point set to 0: {e}")

    return adjusted_start, start, fitness_values[max_fitness_index]


def merge_overlaps(overlap1, overlap2):
    # Initialize the sequence matcher with the overlaps
    seq_matcher = SequenceMatcher(None, overlap1, overlap2)

    # Get the matching blocks
    matching_blocks = seq_matcher.get_matching_blocks()

    # Initialize the merged overlap
    merged_overlap = ""

    # Add the non-matching part before the first matching block
    first_block = matching_blocks[0]
    if first_block.a > 0 and first_block.b > 0:
        # if the first block does not start at the first character,
        # add the appropriate part from the respective overlaps
        merged_overlap += overlap1[:first_block.a] if first_block.a <= len(overlap1) / 2 else overlap2[:first_block.b]

    # Iterate over the matching blocks
    for i, block in enumerate(matching_blocks):
        # Add the matching section to the merged overlap
        merged_overlap += overlap1[block.a:block.a + block.size]

        # Check if we are not at the last block
        if block != matching_blocks[-1]:
            # Determine the position of the non-matching section
            non_matching_position = block.a + block.size
            next_block = matching_blocks[i + 1]

            # Check if we are in the first or second half of the overlap
            if non_matching_position < len(overlap1) / 2:
                # If we are in the first half, add the non-matching section from overlap1
                merged_overlap += overlap1[non_matching_position:next_block.a]
            else:
                non_matching_position = block.b + block.size
                # If we are in the second half, add the non-matching section from overlap2
                merged_overlap += overlap2[non_matching_position:next_block.b]

    return merged_overlap


def stitch_texts(text1, text2):
    # Compute the start of the overlap
    adj_start1, start1, fitness1 = get_overlap_start(text1, text2)

    # Compute the end of the overlap by reversing the texts and computing the start of the overlap
    adj_end2, end2, fitness2 = get_overlap_start(text2[::-1], text1[::-1], adjust_backwards=False)
    adj_end2 = len(text2) - adj_end2
    end2 = len(text2) - end2

    if len([x for x in [fitness1, fitness2] if x != 0]) == 1:
        print(f"only one fitness value is 0 with secondary {text2}")
    overlap1 = text1[adj_start1:] if fitness1 != 0 else ""
    overlap2 = text2[:adj_end2] if fitness2 != 0 else ""
    overlap_merged = merge_overlaps(overlap1, overlap2)

    # Return the stitched text
    return text1[:adj_start1], overlap_merged, text2[adj_end2:]


# TODO: make more robust against unusual inputs (empty strings, etc.)
def knit_texts(text_chunks):
    # create new list for corrected texts
    processed_chunks = []

    # correct for repetition errors (Whisper sometimes repeats sentences multiple times for no apparent reason)
    pattern = re.compile(r'(\D+?)\1{2,}')
    for text in text_chunks:
        processed_chunks.append(pattern.sub(r'\1', text))

    # start final result with 0th time stamp and first half of first text chunk
    result = "[" + convert_to_duration(0) + "] " + processed_chunks[0]

    # iterate through all text chunks, stitch second half of previous chunk to first half of latter chunk
    for index, value in enumerate(processed_chunks[1:]):
        # calculate the base string on which to stitch the next chunk
        # take last MAXIMUM_OVERLAP_LENGTH characters of current result if it is longer, otherwise just the whole result
        base = result[-MAXIMUM_OVERLAP_LENGTH:] if len(result) > MAXIMUM_OVERLAP_LENGTH else result

        rest1, overlap_text, rest2 = stitch_texts(base, value)
        result = result[:-MAXIMUM_OVERLAP_LENGTH] + rest1
        result += " [" + convert_to_duration((index + 1) * PIECE_LENGTH) + "]"

        # check if overlap exists (in case, nothing was said during that time frame)
        if overlap_text:
            result += overlap_text if " " in [overlap_text[0], result[-1]] else " " + overlap_text
        # check if rest2 exists (in case, nothing was said during that time frame)
        if rest2:
            result += rest2 if " " in [rest2[0], result[-1]] else " " + rest2
    return result


def convert_to_duration(count_seconds):
    return f'{count_seconds // 3600:02d}:{count_seconds % 3600 // 60:02d}:{count_seconds % 60:02d}'

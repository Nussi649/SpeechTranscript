from difflib import SequenceMatcher
import statistics
import json
import csv
import re
from tkinter import filedialog

from Tools import get_file_duration

# Define the length of each piece in seconds
PIECE_LENGTH = 15
MINIMUM_MATCH_THRESHOLD = 0.5
MAXIMUM_OVERLAP_LENGTH = 200
total_statistics = []

def get_space_positions(text):
    return [i for i, char in enumerate(text) if char == ' ']


def get_overlap_start(primary, secondary, initial_window_size, threshold=0.9, adjust_backwards=True):
    # Check if the texts are not empty or just jibberish
    if not primary.strip() or not secondary.strip():
        print("Alert: One or both of the texts are empty or contain only whitespace!")
        return -1, -1, -1

    # Convert window_size from word count to character count
    spaces = get_space_positions(primary)

    # Initialize the sequence matcher
    seq_matcher = SequenceMatcher()

    # Initialize the maximum ratio and the start positions
    max_ratio = 0
    start = 0
    window_size = initial_window_size

    requiredRetries = -1

    # Iterate until the ratio exceeds the threshold
    while max_ratio < threshold and window_size > 0:
        requiredRetries += 1
        window_size1 = len(primary) - spaces[- window_size + 1] if window_size <= len(spaces) else len(primary)
        # Iterate over the first text
        for i in range(len(primary) - window_size1 + 1):
            # Set the sequences to match
            seq_matcher.set_seqs(primary[i:i + window_size1], secondary[:window_size1])

            # Compute the ratio
            ratio = seq_matcher.ratio()

            # If the ratio is higher than the maximum found so far, update the maximum and the start positions
            if ratio > max_ratio:
                max_ratio = ratio
                start = i

        # Decrease the window size for the next iteration
        window_size -= 1

    if window_size == 0 and max_ratio < threshold:
        print(f"Alert: The overlap detection algorithm only found {max_ratio} match with {primary[start:]}")
        return -1, -1, -1

    # Find the position of the nearest space that is less than or equal to the start position
    adjusted_start = 0
    try:
        adjusted_start = max(space for space in spaces if space <= start) if adjust_backwards else \
            min(space for space in spaces if space >= start)
    except Exception as e:
        print(f"Starting point set to 0: {e}")

    return adjusted_start, start, requiredRetries


def get_overlap_start_v2(primary, secondary, adjust_backwards=True, max_window_size=30):
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
    for window_size_words in range(1, max_window_size + 1):
        # calculate character count of last 'window_size_words' words in primary
        # if there are as many words in primary as 'window_size_words' then set window length to full length of primary
        window_size_chars = len(primary) - (spaces[-window_size_words] if window_size_words < len(spaces) else 0)

        # Set the sequences to match
        seq_matcher.set_seqs(primary[-window_size_chars:], secondary[:window_size_chars])

        # Compute the ratio
        ratio = seq_matcher.ratio()

        # Store the window size, start position, and ratio
        results.append((window_size_words, len(primary) - window_size_chars, ratio))

        # if the window size counted in words is already longer than primary, don't bother increasing it
        if window_size_words > len(spaces):
            break

    # Compute fitness values and find the maximum
    fitness_values = [fitness_function(len(primary) - start, ratio) for _, start, ratio in results]
    max_fitness_index = fitness_values.index(max(fitness_values))

    total_statistics.append((zip(results, fitness_values), secondary))

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


def stitch_texts(text1, text2):
    # Compute the start of the overlap
    adj_start1, start1, fitness1 = get_overlap_start_v2(text1, text2)

    # Compute the end of the overlap by reversing the texts and computing the start of the overlap
    adj_end2, end2, fitness2 = get_overlap_start_v2(text2[::-1], text1[::-1], adjust_backwards=False)
    adj_end2 = len(text2) - adj_end2
    end2 = len(text2) - end2

    if len([x for x in [fitness1, fitness2] if x != 0]) == 1:
        print(f"only one fitness value is 0 with secondary: {text2}")
    overlap1 = text1[adj_start1:] if fitness1 != 0 else ""
    overlap2 = text2[:adj_end2] if fitness2 != 0 else ""
    overlap_merged = merge_overlaps(overlap1, overlap2)

    # Return the stitched text
    return text1[:adj_start1], overlap_merged, text2[adj_end2:]


def test_overlap_detection(lines):
    with open("Transcription/overlaps_test_adj.txt", "w", encoding="utf-8") as outFile:
        for i in range(len(lines) - 1):
            text1 = lines[i]
            text2 = lines[i+1]

            # Compute the start of the overlap
            adj_start1, start1, fitness1 = get_overlap_start_v2(text1, text2)

            # Compute the end of the overlap by reversing the texts and computing the start of the overlap
            adj_end2, end2, fitness2 = get_overlap_start_v2(text2[::-1], text1[::-1], adjust_backwards=False)
            adj_end2 = len(text2) - adj_end2
            end2 = len(text2) - end2

            if len([x for x in [fitness1, fitness2] if x != 0]) == 1:
                print(f"only one fitness value is 0 in line {i}")
                continue
            overlap1 = text1[start1:] if fitness1 != 0 else ""
            overlap2 = text2[:end2] if fitness2 != 0 else ""
            overlap_merged = merge_overlaps(overlap1, overlap2)

            outFile.write(overlap1 + "\n" + overlap_merged + "\n" + overlap2 + "\n\n")
            print(f"Processed line {i}")


def write_length_ratio_results():
    stuff = list(enumerate(total_statistics))
    # Initialize the CSV writer
    with open("Transcription/length_ratio_results.csv", "w", newline="") as file:
        writer = csv.writer(file, delimiter=';')

        # Write the header row
        writer.writerow(["Sample Index", "Window Size", "Start Position", "Match Ratio", "Fitness Value"])

        for index, entry in stuff:
            # Write each result along with the corresponding fitness value
            for (window_size, start, ratio), fitness in entry[0]:
                ratio_str = "{:.2f}".format(ratio).replace('.', ',')
                fitness_str = "{:.2f}".format(fitness).replace('.', ',')
                writer.writerow([index, window_size, start, ratio_str, fitness_str])

    with open("Transcription/indizes.csv", "w", newline="") as file:
        writer = csv.writer(file, delimiter=';')
        writer.writerow(["Index", "Content"])

        for index, entry in stuff:
            writer.writerow([index, entry[1]])


def test_stats(lines):
    stats = []
    for i in range(50):
        start, delta, retries = get_overlap_start(lines[i], lines[i + 1], 13)

        print("Stats at index {0}: Delta {1}, Retries {2}".format(i, delta, retries))
        stats.append((delta, retries))
    print("Maximum delta: " + str(max(delta for delta, retries in stats)))
    print("Average delta: " + str(statistics.mean([delta for delta, retries in stats])))


def compare_results1(lines):
    final_results = {}
    for threshold in range(70, 90, 1):
        start_indizes = []
        for i in range(len(lines) - 1):
            try:
                adjusted_start, start, _ = get_overlap_start(lines[i], lines[i+1], 15, threshold/100.0)
                # Change here to compare adjusted start indizes (to coincide with space) or calculated start indizes ---
                start_indizes.append(adjusted_start)
            except Exception as e:
                print(f"Error at line {i} with threshold {threshold}: {e}")
                start_indizes.append(None)
            if i % 20 == 0:  # adjust this number based on how frequent you want the updates
                print(f"Progress: at line {i}, threshold {threshold}")
        final_results[str(threshold)] = start_indizes
        print("reached threshold {0}".format(threshold))
    with open("Transcription/statistics.json", "a", encoding="utf-8") as outFile:
        json.dump(final_results, outFile)


def compare_results(lines):
    with open('Transcription/statistics.csv', 'w', newline='') as file:
        writer = csv.writer(file)
        # Write the header
        writer.writerow(['Threshold', 'Line', 'Start_Index'])

        for threshold in range(70, 90, 1):
            for i in range(len(lines) - 1):
                try:
                    adjusted_start, start, _ = get_overlap_start(lines[i], lines[i+1], 15, threshold/100.0)
                    # Change here to compare adjusted start indizes (to coincide with space) or calculated start indizes
                    writer.writerow([threshold, i, adjusted_start])
                except Exception as e:
                    print(f"Error at line {i} with threshold {threshold}: {e}")
                    writer.writerow([threshold, i, None])
                if i % 10 == 0:  # adjust this number based on how frequent you want the updates
                    print(f"Progress: at line {i}, threshold {threshold}")
            print("reached threshold {0}".format(threshold))


def merge_overlaps(overlap1, overlap2):
    # Initialize the sequence matcher with the overlaps
    seq_matcher = SequenceMatcher(None, overlap1, overlap2)

    # Get the matching blocks
    matching_blocks = seq_matcher.get_matching_blocks()

    # Initialize the merged overlap
    merged_overlap = ""

    # Add the non-matching part before the first matching block
    first_block = matching_blocks[0]
    if first_block.a > 0:
        # if the first block does not start at the first character,
        # add the appropriate part from the respective overlaps
        merged_overlap += overlap1[:first_block.a] if first_block.a <= len(overlap1) * 0.8 else overlap2[:first_block.b]

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
            if (non_matching_position + next_block.a) / 2 < len(overlap1) * 0.65:
                # If we are in the first half, add the non-matching section from overlap1
                merged_overlap += overlap1[non_matching_position:next_block.a]
            else:
                non_matching_position = block.b + block.size
                # If we are in the second half, add the non-matching section from overlap2
                merged_overlap += overlap2[non_matching_position:next_block.b]

    return merged_overlap


def convert_to_duration(count_seconds):
    return f'{count_seconds // 3600:02d}:{count_seconds % 3600 // 60:02d}:{count_seconds % 60:02d}'


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


if __name__ == '__main__':

    text_lines = []
    with open("Transcription/output_long.txt", "r", encoding="utf-8") as inFile:
        for line in inFile:
            line = line.strip()  # Remove leading/trailing whitespace
            if line:  # Only append non-empty lines
                text_lines.append(line)
    print("Reading complete")
    total_result = knit_texts(text_lines)
    with open("Transcription/output.txt", "w", encoding="utf-8") as outFile:
        outFile.write(total_result)
    write_length_ratio_results()

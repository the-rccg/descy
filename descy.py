"""
Descy - the word description supplier

by RCCG
"""

# 1. get word
# 2. check if word is common, else next
# 3. check if word has occurred before, else next
# 4. if acronym, add explanation
# 5. check if next word makes it common
# 6. if single word, add definition / explanation
# 7. if compound, add definition / explanation

import re
from wordfreq import word_frequency
import wikipedia
import json
from pprint import pprint
import numba as nb


format_chars   = ['^', '~', '_']
sentence_chars = ['.',',','?','!',';',':']
brackets_chars = ['(',')','[',']','{','}']
equation_chars = ['=','*','/','+','-','µ']
business_chars = ['$','§','#','%']
language_chars = ['"', "'"]
#ignore_chars = set(sentence_chars + equation_chars + business_chars + language_chars)
split_chars = set(
    [' ', '\n', '"', '`', '´'] 
    + sentence_chars 
    + brackets_chars 
    + equation_chars 
    + business_chars
    )


def print_settings(**kwargs):
    ''' print settings pretty '''
    max_length = max([len(word) for word in list(kwargs.keys())])
    format_str = ("{:>"+("{}".format(max_length))+"}: {}")
    for kw, val in kwargs.items():
        print(format_str.format(kw, val))
    return

def descy(filepath, description_file='', freq_cutoff=0.0, bold=True, italic=False, debug=False, use_wiki_desc=True):
    '''
    run through file to find words that are uncommon and explain these
    
    Experimental Parameters:
      freq_cutoff :  defines what gets explained by usage in normal language. scale = (0,1)
    '''

    print_settings(filepath=filepath, description_file=description_file, freq_cutoff=freq_cutoff, bold=bold, italic=italic, debug=debug, use_wiki_desc=use_wiki_desc)

    # Read File
    f = open(filepath, "r", encoding='utf-8')
    # Get Descriptions
    def_dict = load_word_definitions(description_file)
    # Create result list with pointers to strings
    #line_count = []
    out_list = []#'' for _ in range(line_count)]
    explained_words = []
    started = False
    # Loop over line wise
    for line_idx, raw_str in enumerate(f):
        # TODO: Skip till start of document
        if not started:
            if "\\begin{document}" in raw_str:
                started = True
            else: 
                continue
        # Line values
        #raw_str = f[line_idx].read().rstrip()+' '  # one trailing white space allows spliting by white space
        raw_str = raw_str.rstrip()+' '
        out_str = ''
        # Set up loop
        prev_raw_idx = -1     # previous index
        is_beginning = True   # is it still the beginning of the word?
        is_command = False    # is it a latex code?
        last_command = ''     # what was the last command
        last_word = ''        # what was the las word
        ignore = False        # ignore this index
        changed = False       # has this line been changed
        # Run through line character wise
        for raw_idx in range(len(raw_str)):
            ignore = False

            # 0. Check if it's the beginning
            if raw_idx == prev_raw_idx + 1:
                is_beginning = True
            else:
                is_beginning = False

            # 1. Check if comment
            if raw_str[raw_idx] == '%':
                # Escape handling
                if raw_idx > 0:
                    if raw_str[raw_idx-1]!="\\":
                        break
                else:
                    break

            # 2. Starting white spaces should be preserved
            if is_beginning and in_split_chars(raw_str[raw_idx]):
                out_str = out_str + raw_str[raw_idx]
                prev_raw_idx = raw_idx
                continue

            # 3. Split by list to find word
            if raw_str[raw_idx] in split_chars:
                # TODO: Allow n-grams
                # TODO: Find duplicate explanations & remove those
                # TODO: Recognize names through capitalization
                word = raw_str[prev_raw_idx+1:raw_idx]
                if (len(word) >= 2) and (word not in explained_words):
                    word_code, def_dict, explained_words = get_word_code(word, explained_words, def_dict, 
                            freq_cutoff, bold, italic, use_wiki_desc, debug=debug)
                    if word_code != word:
                        changed = True
                    # Add Word and separator
                    out_str = out_str + word_code
                else:
                    out_str = out_str + word
                prev_raw_idx = raw_idx  # Reset
                last_word = word

            # 4.1 Check for command
            if raw_str[raw_idx] == "\\":
                command_start_idx = raw_idx
                is_command = True
                ignore = True

            # 4.2 Check for end of command call
            elif is_command:
                ignore = True
                if raw_str[raw_idx] == '{':
                    command_stop_idx = raw_idx
                    last_command = raw_str[command_start_idx+1:command_stop_idx]
                    is_command = False

            # 4.3 Check for close of command section
            elif raw_str[raw_idx] == '}':
                command_close_idx = raw_idx
                # Find definitions or descriptions already given
                if last_command == '\\footnote{':
                    found_description = raw_str[command_stop_idx+1:command_close_idx]
                    # Determine word that is annotated
                    word = raw_str[prev_raw_idx+1:command_start_idx]
                    # if there was a space in between  TODO: remove space
                    if not word:
                        word = last_word
                    print("Found {}:  {}".format(word, found_description))
                    # Add to definitions
                    def_dict[word] = found_description
                    # TODO: Remove description if it already was defined

            # 5. Ignore special characters
            elif raw_str[raw_idx] in split_chars:
                ignore = True

            # 6. Otherwise normal character
            else:
                # Don't add each character, only add entire words at a time
                continue

            # Wrap-up
            if ignore:
                # TODO: Bulk adjustments
                out_str = out_str + raw_str[raw_idx]
                # word hasn't begun yet
                if is_beginning:
                    prev_raw_idx = raw_idx

        # print before & after in debug mode
        if debug and changed:
            print(line_idx, raw_str)
            print("{} {}".format(" "*len(str(line_idx)), out_str))

        out_list.append(out_str) #[line_idx] = out_str
    # Close file
    #f.close()  # TODO: Creates problem
    if debug:
        pprint(def_dict[word])
    # From dict to string
    if not debug:
        # Overwrite previous text
        f = open(filepath, 'w')
        for out_str in out_list:
            f.write(out_str)
            f.write('\n')
        # Save descriptions
        json.dump(def_dict, description_file)
    return True


def get_word_code(word, explained_words, def_dict, freq_cutoff, bold, italic, use_wiki_desc, debug=False):
    ''' get proper formatted word back '''
    # Do stuff with word
    word_freq = get_word_frequency(word)
    # Is it uncommon?
    if freq_cutoff > 0.00001:
        print("Do not use such a high cutoff")
    word_code = word
    if word_freq <= freq_cutoff:
        # Has it not been explained yet?
        if word.lower() not in explained_words:
            # Get description
            description, def_dict = get_word_description(word, explained_words, def_dict, use_wiki_desc)
            if description:
                if word in description:
                    # TODO: Allow Acronym finding separate from allowing wikipedia descriptions
                    # Acronym formatting
                    if is_acronym(word):
                        full_acronym = get_acronym(word, description)
                        if full_acronym:
                            word_code = "{} ({})".format(full_acronym, word_code)
                            word_code = add_formatting(word_code, bold, italic)
                            print(word_code)
                        else:
                            # acronym not found in description....
                            # Add description as footnote
                            word_code = add_formatting(word_code, bold, italic)
                            word_code = add_latex_footnote(word_code, description)
                    else:
                        # Add description as footnote
                        word_code = add_formatting(word_code, bold, italic)
                        word_code = add_latex_footnote(word_code, description)
                    explained_words.append(word)
    return word_code, def_dict, explained_words


#@nb.njit()
def in_split_chars(char):
    ''' is character in split_list '''
    if char in split_chars:
        return True
    else:
        return False


def add_formatting(word, bold, italic):
    ''' format word wih bold and italic '''
    if bold:
        word_code = '\textbf{' + word + '}'
    if italic:
        word_code = '\textit{' + word_code + '}'
    return word


def get_word_frequency(word):
    ''' get word frequency in ordinary language given word '''
    return word_frequency(word, 'en', wordlist='best', minimum=0.0)


def load_word_definitions(filepath):
    ''' return dict of word definitions from pre-specified file '''
    if filepath:
        filetype = filepath.split('.')[-1].lower()
        if filetype == 'json':
            definitions = json.load(filepath)
        else:
            #print('could not load definitions')
            definitions = {}
    else:
        #print('no definitions file specified')
        definitions = {}
    return definitions


def get_word_description(word, explained_words, def_dict, use_wiki_desc):
    ''' get word descripion
    
    wrapper function for different pathways to get definitions
    '''
    # Get definition
    if word in def_dict:
        description = def_dict[word]
    else:
        # Look in Wikipedia
        if use_wiki_desc:
            description = get_wikipedia_summary(word)
            if description:
                description = '"' + description + '"'
            def_dict[word] = description
        # TODO: allow Oxford English Dictionary, etc.
        # Otherwise screwed
        else:
            description = ''
    return description, def_dict


def get_wikipedia_summary(word):
    ''' get summary of word's wikipedia page '''
    # TODO: Determine contextually the appropriate word
    # TODO: Save category of word
    # TODO: Pull out citations from wikipedia and add them to bibliography
    # TODO: Replace wikipedia citations
    # Alternatively better option:
    #import pywikibot
    #https://en.wikiversity.org/wiki/MediaWiki_API/Pywikibot
    try:
        summary = wikipedia.summary(word, sentences=1)
    except:
        try:
            # search and pick first
            #print('{}: failed to call page'.format(word))
            search_words = wikipedia.search(word)
            word = search_words[0]
            summary = wikipedia.summary(word, sentences=1)
        except:
            #print('{}: failed to find article'.format(word))
            summary = ''
    return summary


def get_word_categories(word):
    ''' return categories associated with the word: e.g. Mahematics, Sailing, etc. '''
    # TODO
    return


def is_acronym(word):
    ''' is the word an acronym? '''
    if (word == word.upper()) and (len(word) >= 2):
        return True
    else:
        return False


def get_acronym(acronym, description):
    ''' return the full name of an acronym '''
    # NOTE: Weird physics abbreviations not yet supported....
    # e.g. GALEX = GALaxy Evolution eXplorer
    words_before_abbrev = description[:description.find(acronym)].strip().split(' ')
    rev_name = []
    for letter in acronym[::-1]:
        # Check if failed
        if len(words_before_abbrev) == 0:
            return False
        # Look for word it stands for 
        for word in words_before_abbrev[::-1]:
            words_before_abbrev.remove(word)  # only check once. CREATES COPY
            # Does the word start with the right letter?
            if word[0] == letter:
                rev_name.append(word)
                break
    return " ".join(rev_name[::-1])


def add_latex_footnote(word, description):
    ''' insert explanation as latex footnote into text '''
    return word + '\\footnote{' + description + '}'


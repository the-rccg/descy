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
import logging
from wordfreq import word_frequency
import wikipedia
import json
from pprint import pprint
import numba as nb
import os
import datetime
now = datetime.datetime.now

format_chars   = ['^', '~', '_', '\\_', '\t']
sentence_chars = ['.',',','?','!',';',':']
brackets_chars = ['(',')','[',']','{','}']
equation_chars = ['=','*','/','+','µ']
business_chars = ['$','§','#','%']
language_chars = ['"', "'"]
numerals_chars = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
#ignore_chars = set(sentence_chars + equation_chars + business_chars + language_chars)
split_chars = set(
    [' ', '\n', '"', '`', '´']
    + format_chars
    + sentence_chars 
    + brackets_chars 
    + equation_chars 
    + business_chars
    + language_chars
    + numerals_chars
)


def print_kwargs(**kwargs):
    ''' print settings pretty '''
    max_length = max([len(word) for word in list(kwargs.keys())])
    format_str = ("{:>"+("{}".format(max_length))+"}: {}")
    for kw, val in kwargs.items():
        print(format_str.format(kw, val))
    return

def string_kwargs(**kwargs):
    ''' kwargs as pretty string '''
    string_list = []
    max_length = max([len(word) for word in list(kwargs.keys())])
    format_str = ("{:>"+("{}".format(max_length))+"}: {}")
    for kw, val in kwargs.items():
        string_list.append(format_str.format(kw, val))
    return "\n".join(string_list)


class descy(object):

    def __init__(self, description_file='', freq_cutoff=0.0, 
                 ignore_file='',
                 bold=True, italic=False, debug=False, use_wiki_desc=True, save_defs=True):
        '''
        Experimental Parameters:
        freq_cutoff :  defines what gets explained by usage in normal language. scale = (0,1)
        '''
        self.start_time = now()
        self.description_file = description_file
        self.freq_cutoff = freq_cutoff
        self.filepath = ""
        self.bold = bold
        self.italic = italic
        self.debug = debug
        self.use_wiki_desc = use_wiki_desc
        self.save_defs = save_defs

        # Create Local Vars
        self.file_history = []
        self.last_run_times = {}
        self.ignore_text = set([])

        # Start Logger
        self.logger = logging.getLogger(__name__)
        self.logger.info(self.settings_str())

        # Load Data into Vars
        self.descriptions = self.load_word_definitions(description_file)
        self.load_ignore_file("\\".join(__file__.split("\\")[:-1]+["\\ignore_text.txt"]))
        if ignore_file:  self.load_ignore_file(ignore_file)
        
        return 


    def load_ignore_file(self, filepath):
        ''' Load words from file into ignore list '''
        new_words = []
        f = open(filepath, "r", encoding='utf-8')
        for _, raw_str in enumerate(f):
            new_words += raw_str.split(" ")
        self.ignore_text = self.ignore_text.union(set(new_words))
        return True


    def __repr__(self):
        ''' print settings '''
        return self.settings_str()


    def settings_str(self):
        return string_kwargs(start_time=self.start_time,
                             filepath=self.filepath, 
                             description_file=self.description_file, 
                             freq_cutoff=self.freq_cutoff, 
                             bold=self.bold, 
                             italic=self.italic,
                             debug=self.debug, 
                             use_wiki_desc=self.use_wiki_desc)


    def run(self, filepath):
        ''' run through file to find words that are uncommon and explain these '''
        run_start_time = now()
        # Read File
        filetype = self.get_filetype(filepath)
        self.logger.info('running through: {}'.format(filepath))
        f = open(filepath, "r", encoding='utf-8')
        # Create result list with pointers to strings
        #line_count = []
        out_list = []#'' for _ in range(line_count)]
        explained_words = []
        started = False
        # Loop over line wise
        for line_idx, raw_str in enumerate(f):
            # Skip until the start of the document
            if not started:
                if "\\begin{document}" in raw_str:
                    started = True
                else: 
                    continue
            # Line Strings
            raw_str = raw_str.rstrip()+' '  # one trailing white space allows spliting by white space
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
            last_time = now()
            for raw_idx in range(len(raw_str)):
                # Ignore Character?
                ignore = False

                # 0. Check if it's the beginning
                if raw_idx == prev_raw_idx + 1:
                    is_beginning = True
                else:
                    is_beginning = False

                # 1. Check if comment
                if raw_str[raw_idx] == '%':  # TeX comment
                    # Escape handling
                    if raw_idx > 0:
                        if raw_str[raw_idx-1] != "\\":  # TeX Escape
                            break
                    else:
                        break

                # 2. Starting white spaces should be preserved
                if is_beginning and self.in_split_chars(raw_str[raw_idx]):
                    out_str = out_str + raw_str[raw_idx]
                    prev_raw_idx = raw_idx
                    continue

                # 3.1 Check for command
                if raw_str[raw_idx] == "\\":
                    command_start_idx = raw_idx
                    is_command = True
                    ignore = True

                # 3.2 Check for end of command call
                if is_command:
                    ignore = True
                    if raw_str[raw_idx] in split_chars:
                    #if raw_str[raw_idx] == '{':
                        command_stop_idx = raw_idx
                        last_command = raw_str[command_start_idx+1:command_stop_idx]
                        is_command = False

                # 3.3 Check for close of command section
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
                        # Update if required
                        self.descriptions = self.update_from_description(self.descriptions, word, 
                                found_description)

                # 4. Split by list to find word
                elif (raw_str[raw_idx] in split_chars):# and (not is_command):
                    # TODO: Allow n-grams
                    # TODO: Find duplicate explanations & remove those
                    # TODO: Recognize names through capitalization
                    word = raw_str[prev_raw_idx+1:raw_idx]
                    # if:  word & not explained
                    if (len(word) >= 2) and (word not in explained_words) and ("--" not in word):
                        word_code, explained_words = self.get_word_code(word, explained_words)
                        if word_code != word:
                            changed = True
                        # Add Word and separator
                        out_str = out_str + word_code + raw_str[raw_idx]
                    else:
                        out_str = out_str + word + raw_str[raw_idx]
                    prev_raw_idx = raw_idx  # Reset
                    last_word = word

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
            if self.debug and changed:
                print(line_idx, raw_str)
                print("{} {}".format(" "*len(str(line_idx)), out_str))

            out_list.append(out_str) #[line_idx] = out_str

            cycle_time = now()-last_time
            if cycle_time > datetime.timedelta(seconds=10):
                print(cycle_time, word)
            last_time = now()

        # Run timing
        run_finish_time = now()
        runtime = run_finish_time - run_start_time
        self.add_runtime(filepath, runtime)
        if self.debug:
            print("Run Time: {}".format(runtime))

        # Close file
        #f.close()  # TODO: Creates problem
        if self.debug:
            pprint(self.descriptions)
        #self.save_file(filepath, out_list)
        self.save_definitions()
        return True


    def add_runtime(self, filepath, runtime):
        ''' add runtime to runtime histories '''
        if filepath not in self.last_run_times.keys():
            self.last_run_times[filepath] = [runtime]
        else:
            self.last_run_times[filepath].append(runtime)
        return


    @staticmethod
    def get_filetype(filename):
        return filename.lower().split(".")[-1]


    def save_definitions(self):
        # Save descriptions
        success = False
        if self.save_defs:
            if json.dump(self.descriptions, open(self.description_file, "w"), indent=2):
                self.logger.info('{}: saved {}'.format(now(), self.description_file))
                success = True
        return success


    def save_file(self, filepath, out_list):
        # Overwrite previous text
        if not self.debug:
            f = open(filepath, 'w')
            for out_str in out_list:
                f.write(out_str)
                f.write('\n')
            f.close()
            self.logger.info('{}: saved {:,} lines to {}'.format(now(), len(out_list), filepath))
            return True
        else:
            return False


    # Process Word


    def get_word_code(self, word, explained_words):
        ''' get proper formatted word back '''
        # Do stuff with word
        word_freq = self.get_word_frequency(word)
        # Is it uncommon?
        if self.freq_cutoff > 0.00001:
            print("Do not use such a high cutoff")
        word_code = word
        if word_freq <= self.freq_cutoff:
            # Has it not been explained yet?
            if (word.lower() not in explained_words) and (word.lower() not in self.ignore_text):
                # Get description
                description, self.descriptions = self.get_word_description(
                        word, explained_words, self.descriptions, self.use_wiki_desc)
                if description:
                    if word in description:
                        # TODO: Allow Acronym finding separate from allowing wikipedia descriptions
                        # Acronym formatting
                        if self.is_acronym(word):
                            full_acronym = self.get_acronym(word, description)
                            if full_acronym:
                                word_code = "{} ({})".format(full_acronym, word_code)
                                word_code = self.add_formatting(word_code, self.bold, self.italic)
                                print(word_code)
                            else:
                                # acronym not found in description....
                                # Add description as footnote
                                word_code = self.add_formatting(word_code, self.bold, self.italic)
                                word_code = self.add_latex_footnote(word_code, description)
                        else:
                            # Add description as footnote
                            word_code = self.add_formatting(word_code, self.bold, self.italic)
                            word_code = self.add_latex_footnote(word_code, description)
                        explained_words.append(word)
        return word_code, explained_words


    @staticmethod
    def in_split_chars(char):
        ''' is character in split_list '''
        if char in split_chars:
            return True
        else:
            return False


    # Word Frequency


    @staticmethod
    def get_word_frequency(word):
        ''' get word frequency in ordinary language given word '''
        return word_frequency(word, 'en', wordlist='best', minimum=0.0)


    # Description Tools


    @staticmethod
    def load_word_definitions(filepath):
        ''' return dict of word definitions from pre-specified file '''
        if filepath:
            filetype = filepath.split('.')[-1].lower()
            if filetype == 'json':
                try:
                    definitions = json.load(open(filepath, "r"))
                except FileNotFoundError:
                    print("Description file not found")
                    definitions = {}
                except:
                    definitions = {}
            else:
                #print('could not load definitions')
                definitions = {}
        else:
            #print('no definitions file specified')
            definitions = {}
        return definitions


    def get_word_description(self, word, explained_words, def_dict, use_wiki_desc):
        ''' get word descripion
        
        wrapper function for different pathways to get definitions
        '''
        # Get definition
        if word.lower() in def_dict:
            description = def_dict[word.lower()]
        else:
            # Look in Wikipedia
            if use_wiki_desc:
                description = self.get_wikipedia_summary(word)
                if description:
                    description = '"' + description + '"'
                def_dict[word] = description
            # TODO: allow Oxford English Dictionary, etc.
            # Otherwise screwed
            else:
                description = ''
        return description, def_dict


    @staticmethod
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

    @staticmethod
    def get_word_categories(word):
        ''' return categories associated with the word: e.g. Mathematics, Sailing, etc. '''
        # TODO
        return


    @staticmethod
    def update_from_description(def_dict, word, found_description):
        ''' update defintitons based on found descripion '''
        check_list = ['defined', 'which is', 'that is', '{} is'.format(word.lower())]
        if any(check_list in found_description.lower()):
            print("Found {}:  {}".format(word, found_description))
            # Add to definitions / update if already presen
            def_dict[word] = found_description
        return def_dict


    # Acronym functions


    @staticmethod
    def is_acronym(word):
        ''' is the word an acronym? '''
        if (word == word.upper()) and (len(word) >= 2):
            return True
        else:
            return False


    @staticmethod
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


    # LaTeX formatting


    @staticmethod
    def add_latex_footnote(word, description):
        ''' insert explanation as latex footnote into text '''
        return word + '\\footnote{' + description + '}'


    @staticmethod
    def add_formatting(word, bold, italic):
        ''' format word wih bold and italic '''
        if bold:
            word_code = '\textbf{' + word + '}'
        if italic:
            word_code = '\textit{' + word_code + '}'
        return word

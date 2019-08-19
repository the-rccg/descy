from descy import descy

testfile = 'thesis.tex'
descfile = 'descriptions.json'

d = descy(description_file=descfile, freq_cutoff=0.0, bold=True, italic=False, debug=True,
          save_defs=True)
d.run(testfile)

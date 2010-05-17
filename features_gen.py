#! /usr/bin/python2.6
# by pts@fazekas.hu at Mon May 17 23:03:43 CEST 2010

"""Tool Generate features.html from features.txt.

TODO(pts): Add documentation.
TODO(pts): Make error messages useful.
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import os
import re
import sys

def main(argv):
  if len(argv) > 1:
    input_filename = argv[1]
  else:
    input_filename = os.path.join(os.path.dirname(__file__), 'features.txt')
  if len(argv) > 2:
    output_filename = argv[2]
  else:
    output_filename = os.path.join(os.path.dirname(__file__), 'features.html')

  subjects = []
  subjects_set = set()
  subjects_lower_set = set()
  aspects = []
  aspect = None
  comments = []
  comment_numbers = {}
  print >>sys.stderr, 'info: reading %s' % input_filename
  for line in open(input_filename):
    line = line.rstrip()
    if not line or line.startswith('#'):
      continue
    if line[0].strip():  # Starts unindented.
      aspect = line
      aspects.append((aspect, {}))
      continue
    assert aspect
    subject, evaluation = line.lstrip().split(':', 1)
    assert evaluation.startswith(' ')
    evaluation = evaluation.lstrip()
    if subject not in subjects_set:
      assert subject not in subjects_lower_set
      subjects_set.add(subject)
      subjects_lower_set.add(subject.lower())
      subjects.append(subject)
      assert '<' not in subject, subject
      assert '&' not in subject, subject
    assert subject not in aspects[-1][1]
    assert '\t' not in evaluation
    assert not evaluation.endswith(',')
    assert not re.match(r',[^ ]', evaluation)
    evalclass = evaluation.split(',', 1)[0]
    assert evalclass in ('yes', 'yes++', 'yes--', 'no', 'no++'), (
        aspect, evaluation)
    if evalclass.endswith('++'):
      evalclass = evalclass[:-2] + 'pp'
    elif evalclass.endswith('--'):
      evalclass = evalclass[:-2] + 'mm'
    aspects[-1][1][subject] = (evaluation, evalclass)
  for aspect, evaluations in aspects:
    missing_subjects = subjects_set.difference(evaluations)
    assert not missing_subjects, (aspect, missing)
    # Verify that there are no HTML-unquoted &s.
    assert ('&' not in aspect or 
            '&' not in re.sub(r'&#?[-a-z0-9]+;', '', aspect)), aspect

  print >>sys.stderr, 'info: generating %s' % output_filename
  output = ['<style type="text/css">\n'
            'table.features              { padding: 0px; border-collapse: collapse; }\n'
            'table.features td           { color:#000000; border: 1px solid black; padding: 1px; border-collapse: collapse; }\n'
            'table.features td.subject a { color:#000000; }\n'
            'table.features td.subject   { width: 5.5em; }\n'
            'table.features td.yes       { background: #00DD00; }\n'
            'table.features td.no        { background: #FF0000; }\n'
            'table.features td.yespp     { background: #00FF00; }\n'
            'table.features td.yesmm     { background: #22BB00; }\n'
            'table.features td.nopp      { background: #DD2200; }\n'
            '</style>\n'
            '<table class=features><thead><tr>', '<td></td>']
  for subject in subjects:
    output.append('<td class=subject>%s</td>' % subject)
  output.append('</tr></thead><tbody>\n')
  for aspect, evaluations in aspects:
    output.append('<tr>')
    output.append('<td>%s</td>' % aspect)
    for subject in subjects:
      evaluation, evalclass = evaluations[subject]
      if ',' in evaluation:
        evalhead, comment = evaluation.split(',', 1)
        comment = comment.strip()
        comment_number = comment_numbers.get(comment)
        if comment_number is None:
          comment_number = len(comment_numbers) + 1
          comment_numbers[comment] = comment_number
          comments.append(comment)
        output.append(
             '<td class="subject %s">%s, <a href="#comment%s">%s)</a></td>' %
             (evalclass, evalhead, comment_number, comment_number))
      else:
        output.append('<td class="subject %s">%s</td>' %
                      (evalclass, evaluation))
    output.append('</tr>\n')
  output.append('</tbody></table>\n')
  if comments:
    # TODO(pts): Highlight comment when clicked or hovered / onmouseover.
    output.append('<p>Comments:\n')
    i = 1
    for comment in comments:
      output.append('<br><a name="comment%s"><b>%s)</b></a> %s\n' % (i, i, comment))
      i += 1
  f = open(output_filename, 'w')
  try:
    f.write(''.join(output))
    f.flush()
  finally:
    f.close()
  print >>sys.stderr, 'info: done, generated file://%s' % os.path.abspath(
      output_filename)

if __name__ == '__main__':
  sys.exit(main(sys.argv) or 0)

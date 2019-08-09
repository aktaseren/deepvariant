# Copyright 2019 Google LLC.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from this
#    software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
"""Create a visual report from a VCF file."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import json

import altair as alt
import numpy as np
import pandas as pd
import tensorflow as tf

# "pretty" genotype strings:
REF = 'Ref (0/0)'
HET = 'Het (0/x)'
HOM = 'Hom (x/x)'
UNCALLED = 'Uncalled (./.)'
HET_BOTH = 'Het - both variants (x/y)'

# Establish ordering of bases to keep it consistent
BASES = ['A', 'G', 'T', 'C']

BAR_COLOR1 = '#9c9ede'
BAR_COLOR2 = '#6b6ecf'


def _dict_to_dataframe(dictionary):
  """Turn a dict object into a list of objects."""
  df = pd.DataFrame({'label': dictionary.keys(), 'value': dictionary.values()})
  return df


def _prettify_genotype(genotype):
  """Get more human-readable display name and grouping for a given genotype."""
  pretty = genotype
  group = 'others'
  alleles = json.loads(genotype)
  if len(alleles) == 2:
    g1, g2 = sorted(alleles)
    if g1 == 0 and g2 == 0:
      pretty = REF
      group = 'main'
    elif g1 == -1 and g2 == -1:
      pretty = UNCALLED
    elif g1 == 0 and g2 > 0:
      pretty = HET
      group = 'main'
    elif g1 == g2:
      pretty = HOM
      group = 'main'
    else:
      pretty = HET_BOTH
  return pretty, group


def _build_type_chart(stats):
  """Create a chart of the counts of each variant type."""
  type_labels = ['Insertion', 'Deletion', 'SNV', 'Complex']
  type_data = stats[stats['label'].isin(type_labels)]
  type_chart = alt.Chart(type_data).mark_bar().encode(
      x=alt.X(
          'label', title=None, sort=type_labels, axis=alt.Axis(labelAngle=0)),
      y=alt.Y('value', axis=alt.Axis(title='Count', format='s')),
      tooltip=alt.Tooltip('value', format='.4s'),
      color=alt.Color(
          'label',
          legend=None,
          sort=type_labels,
          scale=alt.Scale(scheme='set1'))).properties(
              width=200, height=200, title='Variant types')
  return type_chart


def _build_tt_chart(stats, tt_ratio):
  """Create a bar chart with the count of transition and transversion counts."""
  tt_labels = ['Transition', 'Transversion']
  tt_data = stats[stats['label'].isin(tt_labels)]
  tt_chart = alt.Chart(tt_data).mark_bar().encode(
      x=alt.X('label', sort=tt_labels, axis=alt.Axis(title=None, labelAngle=0)),
      y=alt.Y('value', axis=alt.Axis(title='Count', format='s')),
      tooltip=alt.Tooltip('value', format='.4s'),
      color=alt.Color(
          'label', legend=None, sort=tt_labels,
          scale=alt.Scale(scheme='teals'))).properties(
              title='Ti/Tv ratio: %f' % tt_ratio, width=150, height=200)
  return tt_chart


def _build_qual_histogram(vis_data):
  """Create the Quality(QUAL) histogram."""
  qual_data = pd.DataFrame(vis_data['qual_histogram'])
  qual_histogram = alt.Chart(qual_data).mark_bar(color=BAR_COLOR1).encode(
      x=alt.X('bin_start', title='QUAL'),
      x2='bin_end',
      y=alt.Y('count', stack=True, axis=alt.Axis(format='s'))).properties(
          width=200, height=200,
          title='Quality score').interactive(bind_y=False)
  return qual_histogram


def _build_gq_histogram(vis_data):
  """Create the Genotype quality (GQ) histogram."""
  # gq = genotype quality, found at :GQ: in FORMAT column of VCF
  gq_data = pd.DataFrame(vis_data['gq_histogram'])
  gq_histogram = alt.Chart(gq_data).mark_bar(color=BAR_COLOR2).encode(
      x=alt.X('bin_start', title='GQ'),
      x2='bin_end',
      y=alt.Y('count', stack=True, axis=alt.Axis(format='s'))).properties(
          width=200, height=200,
          title='Genotype quality').interactive(bind_y=False)
  return gq_histogram


def _build_vaf_histograms(vis_data):
  """Create VAF histograms split by genotype."""
  histogram_json = vis_data['vaf_histograms_by_genotype']
  guides = {REF: 0, HET: 0.5, HOM: 1}
  hist_data = pd.DataFrame()
  for key in histogram_json:
    g = pd.DataFrame(histogram_json[key])
    g['Raw genotype'] = key
    pretty, group = _prettify_genotype(key)
    g['Genotype'] = pretty
    g['Group'] = group
    g['guide'] = guides.get(pretty, None)
    hist_data = hist_data.append(g)

  main_hist_data = hist_data[hist_data['Group'] == 'main']
  other_hist_data = hist_data[hist_data['Group'] == 'others']

  # Histogram bars themselves
  bars = alt.Chart(main_hist_data).mark_bar().encode(
      x=alt.X('bin_start', title='VAF'),
      x2='bin_end',
      y=alt.Y('count', stack=True, axis=alt.Axis(format='s')))
  # Vertical lines
  guides = alt.Chart(main_hist_data).mark_rule().encode(x='guide')
  # Facet into 3 plots by genotype
  genotype_order = [REF, HET, HOM]
  vaf_histograms = (bars + guides).properties(
      width=200, height=200).facet(
          column=alt.Column(
              'Genotype', title='Main genotypes',
              sort=genotype_order)).resolve_scale(y='independent')

  other_vaf_histograms = alt.Chart(other_hist_data).mark_bar().encode(
      x=alt.X('bin_start', title='VAF'),
      x2='bin_end',
      y=alt.Y('count', stack=True, axis=alt.Axis(format='s')),
      column=alt.Column('Genotype', title='Other genotypes')).properties(
          width=150, height=150).resolve_scale(y='independent')
  return vaf_histograms, other_vaf_histograms


def _build_base_change_chart(vis_data):
  """Create the base change chart."""
  base_change_data = pd.DataFrame(
      vis_data['base_changes'], columns=['ref', 'alt', 'Count'])

  bars = alt.Chart(base_change_data).mark_bar().encode(
      x=alt.X('alt', title='to alt'),
      y=alt.Y('Count', axis=alt.Axis(format='s')),
      color=alt.Color(
          'alt', legend=None, sort=BASES, scale=alt.Scale(scheme='category20')),
      tooltip=alt.Tooltip('Count', format='.4s'))
  text = bars.mark_text(dy=-5, fontWeight='bold').encode(text='alt')

  base_change_chart = (bars + text).properties(
      width=100, height=200).facet(
          column=alt.Column(
              'ref', title='Base changes from reference', sort=BASES))
  return base_change_chart


def _build_indel_size_chart(vis_data):
  """Create the indel size chart."""
  indel_size_data = pd.DataFrame(
      vis_data['indel_sizes'], columns=['size', 'count'])
  indel_size_data['type'] = np.where(indel_size_data['size'] > 0, 'Insertions',
                                     'Deletions')
  # using 'size' alone makes bars overlap slightly, so instead use bin_start and
  # bin_end to force each bar to cover exactly one integer position:
  indel_size_data['bin_start'] = indel_size_data['size'] - 0.5
  indel_size_data['bin_end'] = indel_size_data['size'] + 0.5

  indels_linear = alt.Chart(indel_size_data).mark_bar().encode(
      x=alt.X('bin_start', title='size'),
      x2='bin_end',
      y=alt.Y('count', axis=alt.Axis(format='s')),
      color=alt.Color('type', scale=alt.Scale(scheme='set1'))).properties(
          width=400, height=100, title='Indel sizes').interactive(bind_y=False)

  indel_log = alt.Chart(indel_size_data).mark_bar().encode(
      x=alt.X('bin_start', title='size'),
      x2='bin_end',
      y=alt.Y(
          'count',
          axis=alt.Axis(format='s'),
          scale=alt.Scale(type='log', base=10)),
      color=alt.Color('type', scale=alt.Scale(scheme='set1'))).properties(
          width=400, height=100).interactive(bind_y=False)

  indel_size_chart = alt.vconcat(indels_linear, indel_log)
  return indel_size_chart


def _build_all_charts(stats_data, vis_data, sample_name=''):
  """Build all charts and combine into a single interface."""
  stats = _dict_to_dataframe(stats_data)
  # Transform labels, e.g.: insertion_count -> Insertion, snv_count -> SNV
  stats['label'] = stats['label'].str.replace('_count',
                                              '').str.capitalize().replace(
                                                  'Snv', 'SNV')
  tt_ratio = float(
      stats_data['transition_count']) / stats_data['transversion_count']

  # Row 1
  type_chart = _build_type_chart(stats)
  tt_chart = _build_tt_chart(stats, tt_ratio)
  gq_histogram = _build_gq_histogram(vis_data)
  qual_histogram = _build_qual_histogram(vis_data)

  # Row 2
  vaf_histograms, other_vaf_histograms = _build_vaf_histograms(vis_data)

  # Row 3
  base_change_chart = _build_base_change_chart(vis_data)
  indel_size_chart = _build_indel_size_chart(vis_data)

  # Putting it all together
  all_charts = alt.vconcat(
      alt.hconcat(type_chart, tt_chart, gq_histogram,
                  qual_histogram).resolve_scale(color='independent'),
      alt.hconcat(vaf_histograms, other_vaf_histograms),
      alt.hconcat(base_change_chart,
                  indel_size_chart).resolve_scale(color='independent'))

  all_charts = all_charts.properties(title=sample_name)
  all_charts = all_charts.configure_header(
      labelFontSize=16, titleFontSize=20).configure_title(fontSize=20)
  return all_charts


def _save_html(basename, all_charts):
  """Save Altair chart as an HTML file."""
  output_path = basename + '.visual_report.html'
  with tf.io.gfile.GFile(output_path, 'w') as writer:
    all_charts.save(writer, format='html')


def create_visual_report(basename, stats_data, vis_data, sample_name=''):
  """Build visual report with several charts."""
  all_charts = _build_all_charts(stats_data, vis_data, sample_name)
  _save_html(basename, all_charts)

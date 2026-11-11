"""Small synthetic tests for the single owner-approved Stage3 P1 selection."""
from pathlib import Path
import importlib.util
import unittest

MODULE=Path(__file__).resolve().parents[1] / 'scripts' / 'stage3_pilot_prepare.py'
spec=importlib.util.spec_from_file_location('stage3_pilot_prepare', MODULE)
pp=importlib.util.module_from_spec(spec)
spec.loader.exec_module(pp)


def record(source, ident, title=None, abstract=None):
    return {'source_id':source,'source_record_id':ident,'title':title,'abstract':abstract}


class Stage3PilotPrepareTests(unittest.TestCase):
    def test_whole_record_complete_before_title_only(self):
        rows=[record('pubmed','p','PubMed no abstract'),
              record('woscc','w','WoS title','WoS abstract'),
              record('apa_psycinfo','a','APA title','APA abstract')]
        selected=pp.choose_source(rows)
        self.assertEqual(selected['text_state'],'title_abstract')
        self.assertEqual(selected['record']['source_record_id'],'w')
        self.assertEqual(selected['record']['title'],'WoS title')
        self.assertEqual(selected['record']['abstract'],'WoS abstract')

    def test_title_only_requires_no_abstract_in_group(self):
        self.assertEqual(pp.choose_source([record('pubmed','p','Title'),
               record('apa_psycinfo','a',None,'Abstract')])['text_state'],
               'requires_source_resolution')
        chosen=pp.choose_source([record('apa_psycinfo','a','APA'),
                                 record('pubmed','p','PubMed')])
        self.assertEqual(chosen['text_state'],'title_only')
        self.assertEqual(chosen['record']['source_record_id'],'p')
        self.assertEqual(pp.choose_source([record('pubmed','p')])['text_state'],
                         'missing_input')

    def test_deterministic_stratified_ids_no_duplicates(self):
        def row(i):
            return {'article_id':f'a{i:03d}', 'source_id':'pubmed' if i%2 else 'woscc',
                    'text_state':'title_only' if i%7==0 else 'title_abstract',
                    'year_bucket':'year_2020plus' if i%3 else 'year_pre2000',
                    'degree_bucket':'degree_zero' if i%5==0 else 'degree_20plus',
                    'long_abstract_candidate':i%11==0,
                    'peer_review_unknown':i==9,
                    'wos_nr_cr_mismatch':i==13}
        candidates=[row(i) for i in range(200)]
        a=pp.sample(candidates,n=50,per_stratum=5)
        b=pp.sample(list(reversed(candidates)),n=50,per_stratum=5)
        self.assertEqual(a,b)
        self.assertEqual(len({x['article_id'] for x in a}),50)
        self.assertTrue(any(x['peer_review_unknown'] for x in a))
        self.assertTrue(any(x['wos_nr_cr_mismatch'] for x in a))
        with self.assertRaises(ValueError):
            pp.sample([row(1),row(1)],n=2)

if __name__=='__main__':
    unittest.main()

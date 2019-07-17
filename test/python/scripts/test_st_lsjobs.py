# Licensed Materials - Property of IBM
# Copyright IBM Corp. 2019
import unittest
import sys
import os
import time
import requests
import uuid
import glob
import re



from streamsx.topology.topology import Topology
from streamsx.topology.context import submit, ConfigParams
from streamsx.rest import Instance
import streamsx.scripts.streamtool as streamtool


from contextlib import contextmanager
from io import StringIO

@contextmanager
def captured_output():
    new_out, new_err = StringIO(), StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    try:
        sys.stdout, sys.stderr = new_out, new_err
        yield sys.stdout, sys.stderr
    finally:
        sys.stdout, sys.stderr = old_out, old_err

@unittest.skipUnless(
    "ICPD_URL" in os.environ
    and "STREAMS_INSTANCE_ID" in os.environ
    and "STREAMS_USERNAME" in os.environ
    and "STREAMS_PASSWORD" in os.environ,
    "requires Streams REST API setup",
)
class Testlsjobs(unittest.TestCase):

    def _submitjob(self, args, sab=None):
        args.insert(0, "--disable-ssl-verify")
        args.insert(1, "submitjob")
        if sab:
            args.insert(2, sab)
        else:
            topo = Topology()
            topo.source([1])
            cfg = {}
            cfg[ConfigParams.SSL_VERIFY] = False
            src = submit("BUNDLE", topo, cfg)
            sab_path = src["build"]["artifacts"][0]["location"]
            args.insert(2, sab_path)
            self.files_to_remove.append(sab_path)
        rc, val = streamtool.run_cmd(args=args)
        return rc, val

    def _ls_jobs(self, jobs=None, users=None, jobnames=None, fmt=None, xheaders=False, showtimestamp=False):
        args = ["--disable-ssl-verify", "lsjobs"]
        if jobs:
            args.extend(['--jobs', jobs])
        if users:
            args.extend(['--users', users])
        if jobnames:
            args.extend(['--jobnames', jobnames])
        if fmt:
            args.extend(['--fmt', fmt])
        if xheaders:
            args.append('--xheaders')
        if showtimestamp:
            args.append('--showtimestamp')

        return streamtool.run_cmd(args=args)


    def setUp(self):
        self.instance = os.environ["STREAMS_INSTANCE_ID"]
        self.username = os.environ["STREAMS_USERNAME"]
        self.stringLength = 10
        self.jobs_to_cancel = []
        self.files_to_remove = []
        self.my_instance = Instance.of_endpoint(username= self.username, verify=False)
        self.name = "TEST__" + uuid.uuid4().hex.upper()[0 : self.stringLength]

    def tearDown(self):
        for job in self.jobs_to_cancel:
            job.cancel(force=True)

        self.files_to_remove.extend(glob.glob("./test_st_lsjobs.*.json"))

        for file in self.files_to_remove:
            if os.path.exists(file):
                os.remove(file)

    # Split my_string by 2 or more whitespaces
    def split_string(self, my_string):
        return re.split(r'\s{2,}', my_string.strip())

    def check_job(self, job, output):
        job_details = self.split_string(output)
        self.assertEqual(job.id, job_details[0]) # job ID
        self.assertEqual(self.username, job_details[3])  # job user
        self.assertEqual(job.name, job_details[5]) # job name
        self.assertEqual(job.jobGroup.split("/")[-1] , job_details[6]) # job group
        self.assertTrue(len(job_details) == 7)

    def test_lsappconfig_simple(self):
        rc, job = self._submitjob(args=[])
        self.jobs_to_cancel.extend([job])
        output, error, rc= self.get_output(lambda: self._ls_jobs())
        output = output.splitlines()

        # Check instance data output correctly
        instance_string = 'Instance: ' + self.my_instance.id
        self.assertEqual(output[0].strip(), instance_string)

        # Check headers outputs correctly
        true_headers = ["Id", "State", "Healthy", "User", "Date", "Name", "Group"]
        headers = self.split_string(output[1])
        self.assertEqual(true_headers, headers)

        # Check details of job are correct
        self.check_job(job, output[2])
        self.assertEqual(rc, 0)

    def test_lsappconfig_complex(self):
        rc, job1 = self._submitjob(args=['--jobname', self.name])
        rc, job2 = self._submitjob(args=['--jobname', self.name+self.name])
        self.jobs_to_cancel.extend([job1, job2])
        output, error, rc= self.get_output(lambda: self._ls_jobs())
        output = output.splitlines()

        # Check instance data output correctly
        instance_string = 'Instance: ' + self.my_instance.id
        self.assertEqual(output[0].strip(), instance_string)

        # Check headers outputs correctly
        true_headers = ["Id", "State", "Healthy", "User", "Date", "Name", "Group"]
        headers = self.split_string(output[1])
        self.assertEqual(true_headers, headers)

        # Check details of job1 are correct
        self.check_job(job1, output[2])

        # Check details of job2 are correct
        self.check_job(job2, output[3])

        self.assertEqual(rc, 0)

    # Check --jobnames
    def test_lsappconfig_complex_2(self):
        rc, job1 = self._submitjob(args=['--jobname', self.name])
        rc, job2 = self._submitjob(args=['--jobname', self.name+self.name])
        rc, job3 = self._submitjob(args=['--jobname', self.name+self.name+self.name])
        self.jobs_to_cancel.extend([job1, job2, job3])

        output, error, rc= self.get_output(lambda: self._ls_jobs(jobnames=str(job1.name,job3.name)))
        output = output.splitlines()

        # Check it printed out the correct # of jobs (+2 bc it also includes the instance string and the header string)
        self.assertTrue(len(output) == 4)

        # Check instance data output correctly
        instance_string = 'Instance: ' + self.my_instance.id
        self.assertEqual(output[0].strip(), instance_string)

        # Check headers outputs correctly
        true_headers = ["Id", "State", "Healthy", "User", "Date", "Name", "Group"]
        headers = self.split_string(output[1])
        self.assertEqual(true_headers, headers)

        # Check details of job1 are correct
        self.check_job(job1, output[2])

        # Check details of job3 are correct
        self.check_job(job3, output[3])

        self.assertEqual(rc, 0)

    # Check --jobs
    def test_lsappconfig_complex_3(self):
        rc, job1 = self._submitjob(args=['--jobname', self.name])
        rc, job2 = self._submitjob(args=['--jobname', self.name+self.name])
        rc, job3 = self._submitjob(args=['--jobname', self.name+self.name+self.name])
        self.jobs_to_cancel.extend([job1, job2, job3])

        job_ids = str(job1.id) + ',' + str(job3.id)
        output, error, rc= self.get_output(lambda: self._ls_jobs(jobs=job_ids))
        output = output.splitlines()

        # Check it printed out the correct # of jobs (+2 bc it also includes the instance string and the header string)
        self.assertTrue(len(output) == 4)

        # Check instance data output correctly
        instance_string = 'Instance: ' + self.my_instance.id
        self.assertEqual(output[0].strip(), instance_string)

        # Check headers outputs correctly
        true_headers = ["Id", "State", "Healthy", "User", "Date", "Name", "Group"]
        headers = self.split_string(output[1])
        self.assertEqual(true_headers, headers)

        # Check details of job1 are correct
        self.check_job(job1, output[2])

        # Check details of job3 are correct
        self.check_job(job3, output[3])

        self.assertEqual(rc, 0)

    def get_output(self, my_function):
        """ Helper function that gets the ouput from executing my_function

        Arguments:
            my_function {} -- The function to be executed

        Returns:
            Output [String] -- Output of my_function
            Rc [int] -- 0 indicates succces, 1 indicates error or failure
        """
        rc = None
        with captured_output() as (out, err):
            rc, val = my_function()
        output = out.getvalue().strip()
        error = err.getvalue().strip()
        return output, error, rc
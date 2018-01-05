# Copyright (c) 2016-present, Facebook, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##############################################################################

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import unittest

from caffe2.python import workspace, core
import caffe2.python.parallel_workers as parallel_workers


def create_queue():
    queue = 'queue'

    workspace.RunOperatorOnce(
        core.CreateOperator(
            "CreateBlobsQueue", [], [queue], num_blobs=1, capacity=1000
        )
    )

    return queue


def create_worker(queue, get_blob_data):
    def dummy_worker(worker_id):
        blob = 'blob_' + str(worker_id)

        workspace.FeedBlob(blob, get_blob_data(worker_id))

        workspace.RunOperatorOnce(
            core.CreateOperator(
                'SafeEnqueueBlobs', [queue, blob], [blob, 'status_blob']
            )
        )

    return dummy_worker


def dequeue_value(queue):
    dequeue_blob = 'dequeue_blob'
    workspace.RunOperatorOnce(
        core.CreateOperator(
            "SafeDequeueBlobs", [queue], [dequeue_blob, 'status_blob']
        )
    )

    return workspace.FetchBlob(dequeue_blob)


class ParallelWorkersTest(unittest.TestCase):
    def testParallelWorkers(self):
        workspace.ResetWorkspace()

        queue = create_queue()
        dummy_worker = create_worker(queue, lambda worker_id: str(worker_id))
        worker_coordinator = parallel_workers.init_workers(dummy_worker)
        worker_coordinator.start()

        for _ in range(10):
            value = dequeue_value(queue)
            self.assertTrue(
                value in [b'0', b'1'], 'Got unexpected value ' + str(value)
            )

        self.assertTrue(worker_coordinator.stop())

    def testParallelWorkersInitFun(self):
        workspace.ResetWorkspace()

        queue = create_queue()
        dummy_worker = create_worker(
            queue, lambda worker_id: workspace.FetchBlob('data')
        )
        workspace.FeedBlob('data', 'not initialized')

        def init_fun(worker_coordinator, global_coordinator):
            workspace.FeedBlob('data', 'initialized')

        worker_coordinator = parallel_workers.init_workers(
            dummy_worker, init_fun=init_fun
        )
        worker_coordinator.start()

        for _ in range(10):
            value = dequeue_value(queue)
            self.assertEqual(
                value, b'initialized', 'Got unexpected value ' + str(value)
            )

        self.assertTrue(worker_coordinator.stop())

    def testParallelWorkersShutdownFun(self):
        workspace.ResetWorkspace()

        queue = create_queue()
        dummy_worker = create_worker(queue, lambda worker_id: str(worker_id))
        workspace.FeedBlob('data', 'not shutdown')

        def shutdown_fun():
            workspace.FeedBlob('data', 'shutdown')

        worker_coordinator = parallel_workers.init_workers(
            dummy_worker, shutdown_fun=shutdown_fun
        )
        worker_coordinator.start()

        self.assertTrue(worker_coordinator.stop())

        data = workspace.FetchBlob('data')
        self.assertEqual(data, b'shutdown', 'Got unexpected value ' + str(data))
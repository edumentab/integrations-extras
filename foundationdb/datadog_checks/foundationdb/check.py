
from typing import Any

from datadog_checks.base import AgentCheck

# from datadog_checks.base.utils.db import QueryManager
# from requests.exceptions import ConnectionError, HTTPError, InvalidURL, Timeout
import json

from datadog_checks.base.utils.subprocess_output import get_subprocess_output, SubprocessOutputEmptyError


class FoundationdbCheck(AgentCheck):
    def __init__(self, name, init_config, instances):
        super(FoundationdbCheck, self).__init__(name, init_config, instances)

    def construct_cli_base(self, instance):
        # do a copy not to pollute original list
        fdb_args = (instance.get('base_command')[:]
                if 'base_command' in instance
                else ['fdbcli'])

        if 'cluster_file' in instance:
            fdb_args.append('-C')
            fdb_args.append(instance.get('cluster_file'))

        # TLS options
        tls_keys = ['tls_certificate_file', 'tls_key_file', 'tls_verify_peers', 'tls_password', 'tls_ca_file']
        for key in tls_keys:
            if key in instance:
                fdb_args.append('--' + key)
                fdb_args.append(instance.get(key))
        return fdb_args

    def fdb_status_data(self, instance):
        fdb_args = self.construct_cli_base(instance)
        fdb_args.append('--exec')
        fdb_args.append('status json')
        return get_subprocess_output(fdb_args, self.log)

    def check(self, instance):
        try:
            status = self.fdb_status_data(instance)
        except SubprocessOutputEmptyError as e:
            self.service_check("foundationdb.can_connect", AgentCheck.CRITICAL, message="Did not receive a response from `status json`")
            raise

        if status[2] != 0:
            self.service_check("foundationdb.can_connect", AgentCheck.CRITICAL, message="`fdbcli` returned non-zero error code")
            raise ValueError("`fdbcli --exec 'status json'` failed")

        try:
            data = json.loads(status[0])
        except Exception as e:
            self.service_check("foundationdb.can_connect", AgentCheck.CRITICAL, message="Could not parse `status json`")
            raise

        self.check_metrics(data)

    def report_process(self, process):
        if "address" not in process:
            return
        tags = [ "fdb_process:" + process["address"] ]

        if "cpu" in process:
            self.maybe_gauge("foundationdb.process.cpu.usage_cores", process["cpu"], "usage_cores", tags)
        if "disk" in process:
            disk = process["disk"]
            self.maybe_gauge("foundationdb.process.disk.free_bytes", disk, "free_bytes", tags)
            self.maybe_gauge("foundationdb.process.disk.total_bytes", disk, "total_bytes", tags)
            if "reads" in disk:
                self.maybe_gauge("foundationdb.process.disk.reads.hz", disk["reads"], "hz", tags)
                self.maybe_count("foundationdb.process.disk.reads.count", disk["reads"], "count", tags)
            if "writes" in disk:
                self.maybe_gauge("foundationdb.process.disk.writes.hz", disk["writes"], "hz", tags)
                self.maybe_count("foundationdb.process.disk.writes.count", disk["writes"], "count", tags)
        if "memory" in process:
            memory = process["memory"]
            self.maybe_gauge("foundationdb.process.memory.available_bytes", memory, "available_bytes", tags)
            self.maybe_gauge("foundationdb.process.memory.limit_bytes", memory, "limit_bytes", tags)
            self.maybe_gauge("foundationdb.process.memory.unused_allocated_memory", memory, "unused_allocated_memory", tags)
            self.maybe_gauge("foundationdb.process.memory.used_bytes", memory, "used_bytes", tags)
        if "network" in process:
            network = process["network"]
            self.maybe_gauge("foundationdb.process.network.current_connections", network, "current_connections", tags)
            self.maybe_hz_counter("foundationdb.process.network.connection_errors", network, "connection_errors", tags)
            self.maybe_hz_counter("foundationdb.process.network.connections_closed", network, "connections_closed", tags)
            self.maybe_hz_counter("foundationdb.process.network.connections_established", network, "connections_established", tags)
            self.maybe_hz_counter("foundationdb.process.network.megabits_received", network, "megabits_received", tags)
            self.maybe_hz_counter("foundationdb.process.network.megabits_sent", network, "megabits_sent", tags)
            self.maybe_hz_counter("foundationdb.process.network.tls_policy_failures", network, "tls_policy_failures", tags)

        if "roles" in process:
            for role in process["roles"]:
                self.report_role(role, tags)


    def report_role(self, role, process_tags):
        if "role" not in role:
            return
        tags = process_tags + [ "fdb_role:" + role["role"] ]

        self.maybe_hz_counter("foundationdb.process.role.input_bytes", role, "input_bytes", tags)
        self.maybe_hz_counter("foundationdb.process.role.durable_bytes", role, "durable_bytes", tags)
        self.maybe_hz_counter("foundationdb.process.role.total_queries", role, "total_queries", tags)
        self.maybe_hz_counter("foundationdb.process.role.bytes_queried", role, "bytes_queried", tags)
        self.maybe_hz_counter("foundationdb.process.role.durable_bytes", role, "durable_bytes", tags)
        self.maybe_hz_counter("foundationdb.process.role.finished_queries", role, "finished_queries", tags)
        self.maybe_hz_counter("foundationdb.process.role.keys_queried", role, "keys_queried", tags)
        self.maybe_hz_counter("foundationdb.process.role.low_priority_queries", role, "low_priority_queries", tags)
        self.maybe_hz_counter("foundationdb.process.role.mutation_bytes", role, "mutation_bytes", tags)
        self.maybe_hz_counter("foundationdb.process.role.mutations", role, "mutations", tags)
        self.maybe_gauge("foundationdb.process.role.stored_bytes", role, "stored_bytes", tags)
        self.maybe_gauge("foundationdb.process.role.query_queue_max", role, "query_queue_max", tags)
        self.maybe_gauge("foundationdb.process.role.local_rate", role, "local_rate", tags)
        self.maybe_gauge("foundationdb.process.role.kvstore_available_bytes", role, "kvstore_available_bytes", tags)
        self.maybe_gauge("foundationdb.process.role.kvstore_free_bytes", role, "kvstore_free_bytes", tags)
        self.maybe_gauge("foundationdb.process.role.kvstore_inline_keys", role, "kvstore_inline_keys", tags)
        self.maybe_gauge("foundationdb.process.role.kvstore_total_bytes", role, "kvstore_total_bytes", tags)
        self.maybe_gauge("foundationdb.process.role.kvstore_total_nodes", role, "kvstore_total_nodes", tags)
        self.maybe_gauge("foundationdb.process.role.kvstore_total_size", role, "kvstore_total_size", tags)
        self.maybe_gauge("foundationdb.process.role.kvstore_used_bytes", role, "kvstore_used_bytes", tags)

        if "data_lag" in role:
            self.maybe_gauge("foundationdb.process.role.data_lag.seconds", role["data_lag"], "seconds", tags)
        if "durability_lag" in role:
            self.maybe_gauge("foundationdb.process.role.durability_lag.seconds", role["durability_lag"], "seconds", tags)

        if "grv_latency_statistics" in role:
            self.report_statistics("foundationdb.process.role.grv_latency_statistics.default", role["grv_latency_statistics"], "default", tags)

        self.report_statistics("foundationdb.process.role.read_latency_statistics", role, "read_latency_statistics", tags)
        self.report_statistics("foundationdb.process.role.commit_latency_statistics", role, "commit_latency_statistics", tags)

    def report_statistics(self, metric, obj, key, tags=None):
        if key in obj:
            statistics = obj[key]
            self.maybe_count(metric + ".count", statistics, "count", tags=tags)
            self.maybe_gauge(metric + ".min", statistics, "min", tags=tags)
            self.maybe_gauge(metric + ".max", statistics, "max", tags=tags)
            self.maybe_gauge(metric + ".p25", statistics, "p25", tags=tags)
            self.maybe_gauge(metric + ".p50", statistics, "p50", tags=tags)
            self.maybe_gauge(metric + ".p90", statistics, "p90", tags=tags)
            self.maybe_gauge(metric + ".p99", statistics, "p99", tags=tags)


    def check_metrics(self, status):
        if not "cluster" in status:
            raise ValueError("JSON Status data doesn't include cluster data")

        cluster = status["cluster"]
        if "machines" in cluster:
            self.gauge("foundationdb.machines", len(cluster["machines"]))
        if "processes" in cluster:
            self.gauge("foundationdb.processes", len(cluster["processes"]))

            self.count("foundationdb.instances", sum(map(lambda p: len(p["roles"]) if "roles" in p else 0, cluster["processes"].values())))
            for process in cluster["processes"]:
                self.report_process(cluster["processes"][process])

        if "data" in cluster:
            data = cluster["data"]
            self.maybe_gauge("foundationdb.data.system_kv_size_bytes", data, "system_kv_size_bytes")
            self.maybe_gauge("foundationdb.data.total_disk_used_bytes", data, "total_disk_used_bytes")
            self.maybe_gauge("foundationdb.data.total_kv_size_bytes", data, "total_kv_size_bytes")
            self.maybe_gauge("foundationdb.data.least_operating_space_bytes_log_server", data, "least_operating_space_bytes_log_server")

            if "moving_data" in data:
                self.maybe_gauge("foundationdb.data.moving_data.in_flight_bytes", data["moving_data"], "in_flight_bytes")
                self.maybe_gauge("foundationdb.data.moving_data.in_queue_bytes", data["moving_data"], "in_queue_bytes")
                self.maybe_gauge("foundationdb.data.moving_data.total_written_bytes", data["moving_data"], "total_written_bytes")

        if "datacenter_lag" in cluster:
            self.gauge("foundationdb.datacenter_lag.seconds", cluster["datacenter_lag"]["seconds"])

        if "workload" in cluster:
            workload = cluster["workload"]
            if "transactions" in workload:
                transactions = workload["transactions"]
                for k in transactions:
                    self.maybe_hz_counter("foundationdb.workload.transactions." + k, transactions, k)

            if "operations" in workload:
                operations = workload["operations"]
                for k in operations:
                    self.maybe_hz_counter("foundationdb.workload.operations." + k, operations, k)

        if "latency_probe" in cluster:
            for k, v in cluster["latency_probe"].items():
                self.gauge("foundationdb.latency_probe." + k, v)

        degraded_processes = 0
        if "degraded_processes" in cluster:
            self.gauge("foundationdb.degraded_processes", cluster["degraded_processes"])
            degraded_processes = cluster["degraded_processes"]

        if degraded_processes > 0:
            self.service_check("foundationdb.can_connect", AgentCheck.WARNING, message="There are degraded processes")
        else:
            self.service_check("foundationdb.can_connect", AgentCheck.OK)

    def maybe_gauge(self, metric, obj, key, tags=None):
        if key in obj:
            self.gauge(metric, obj[key], tags=tags)

    def maybe_count(self, metric, obj, key, tags=None):
        if key in obj:
            self.monotonic_count(metric, obj[key], tags=tags)

    def maybe_hz_counter(self, metric, obj, key, tags=None):
        if key in obj:
            if "hz" in obj[key]:
                self.gauge(metric + ".hz", obj[key]["hz"], tags=tags)
            if "counter" in obj[key]:
                self.monotonic_count(metric + ".counter", obj[key]["counter"], tags=tags)

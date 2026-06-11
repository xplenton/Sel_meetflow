# Iter 201 — Tasks Module Load Test (200 concurrent users)

**Elapsed:** 27.4s · **Total requests:** 4400 · **Failures:** 0 (0.00%) · **Throughput:** 160.6 req/s


## Per-operation metrics

| Operation | Count | p50 ms | p95 ms | p99 ms | Max ms | Errors |
|---|---:|---:|---:|---:|---:|---|
| add_comment | 200 | 1014 | 1105 | 1191 | 1257 | — |
| add_link | 200 | 795 | 859 | 876 | 878 | — |
| calendar_feed | 200 | 1135 | 1331 | 1473 | 1508 | — |
| create_recurring | 200 | 683 | 718 | 730 | 742 | — |
| create_task | 200 | 696 | 822 | 841 | 849 | — |
| delete_task | 200 | 1852 | 1988 | 2054 | 2066 | — |
| duplicate_task | 200 | 902 | 987 | 1002 | 1005 | — |
| from_template | 200 | 843 | 917 | 980 | 1007 | — |
| get_task | 200 | 792 | 838 | 863 | 869 | — |
| history | 200 | 1088 | 1159 | 1186 | 1186 | — |
| list_filtered | 200 | 1727 | 1958 | 2005 | 2014 | — |
| pending_count | 200 | 1004 | 1078 | 1112 | 1122 | — |
| permissions | 1000 | 370 | 3937 | 4723 | 4900 | — |
| recur_mark_done | 200 | 1638 | 1718 | 1748 | 1752 | — |
| search | 200 | 2145 | 2260 | 2272 | 2343 | — |
| update_priority | 200 | 1408 | 1496 | 1535 | 1538 | — |
| update_status_in_progress | 200 | 1400 | 1495 | 1523 | 1587 | — |
| update_tags | 200 | 1494 | 1552 | 1563 | 1563 | — |

## Error summary

*No errors observed.*
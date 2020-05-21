#!/usr/bin/env python
# -*- coding:utf-8 -*-
# Author:Viki Zhao

import sys
import os
from .tensor.STTensor import loadTensor
from . import system
import importlib
import sqlite3
import scipy.sparse.linalg as slin
from scipy.sparse import csc_matrix, coo_matrix, csr_matrix, lil_matrix

# engine
engine = system.Engine()

# bridges for model and data
anomaly_detection = system.AnomalyDetection()
decomposition = system.Decomposition()
traingle_count = system.TraingleCount()
series_summarization = system.SeriesSummarization()

# model positions
ad_policy, tc_policy, ed_policy, ss_policy = None, None, None, None


def config(frame_name):
    global ad_policy, tc_policy, ed_policy, ss_policy
    frame = importlib.import_module(frame_name)

    # algorithm list
    ad_policy = frame.AnomalyDetection
    tc_policy = frame.TriangleCount
    ed_policy = frame.Decomposition
    ss_policy = frame.SeriesSummarization


def bidegree(edgelist):
    sm = _get_sparse_matrix(edgelist, squared=True)

    sm_csr = sm.tocsr(copy=False)
    sm_csc = sm.tocsc(copy=False)

    # calculate degree
    Du = sm_csr.sum(axis=1).getA1()
    Dv = sm_csc.sum(axis=0).getA1()

    return Du, Dv


'''
def degree(edgelist):
    sm = _get_sparse_matrix(edgelist, True)

    sm_csr = sm.tocsr(copy = False)
    sm_csc = sm.tocsc(copy = False)

    # calculate degree
    Du = sm_csr.sum(axis = 1).getA1()
    Dv = sm_csc.sum(axis = 0).getA1()
    D = Du + Dv

    return D
'''


def _get_sparse_matrix(edgelist, squared=False):
    edges = edgelist[2]
    edge_num = len(edges)

    # construct the sparse matrix
    xs = [edges[i][0] for i in range(edge_num)]
    ys = [edges[i][1] for i in range(edge_num)]
    data = [1] * edge_num

    row_num = max(xs) + 1
    col_num = max(ys) + 1

    if squared:
        row_num = max(row_num, col_num)
        col_num = row_num

    sm = coo_matrix((data, (xs, ys)), shape=(row_num, col_num))

    return sm


def subgraph(edgelist, uid_array, oid_array=None):
    if oid_array == None:
        squared = True
    else:
        squared = False

    # create db connection
    con = sqlite3.connect(":memory:")
    cur = con.cursor()

    # create edge table
    sql_str = '''CREATE TABLE EDGE
                    (id INTEGER PRIMARY KEY AUTOINCREMENT'''
    for i in range(len(edgelist[0])):
        sql_str += ", " + edgelist[0][i] + " " + edgelist[1][i]
    sql_str += ");"
    cur.execute(sql_str)

    # insert data into edge table
    col_ids_str = str(edgelist[0])
    col_ids_length = len(edgelist[0])
    sql_str = "INSERT INTO EDGE " + col_ids_str + " VALUES " + _construct_sql_value_placeholder(col_ids_length)
    cur.executemany(sql_str, edgelist[2])

    # create index for table edge
    sql_str = "CREATE INDEX edge_uid on EDGE ({});".format(edgelist[0][0])
    cur.execute(sql_str)
    sql_str = "CREATE INDEX edge_oid on EDGE ({});".format(edgelist[0][1])
    cur.execute(sql_str)

    # create uid table
    sql_str = '''CREATE TABLE UID
                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 uid INT NOT NULL);'''
    cur.execute(sql_str)

    # insert data into uid table
    sql_str = "INSERT INTO UID (uid) VALUES (?)"
    uid_tuple_array = [(ele,) for ele in uid_array]
    cur.executemany(sql_str, uid_tuple_array)

    # create index for column uid
    sql_str = "CREATE UNIQUE INDEX uid_uid on UID (uid);"
    cur.execute(sql_str)

    # get subgraph edges
    sql_str = "SELECT EDGE." + edgelist[0][0]
    for i in range(1, len(edgelist[0])):
        sql_str += ", EDGE.{}".format(edgelist[0][i])
    sql_str += " FROM EDGE"

    if squared == True:
        sql_str += ''', UID
                      WHERE EDGE.{} = UID.uid
                      AND EDGE.{} = UID.uid;'''.format(edgelist[0][0], edgelist[0][1])
        cur.execute(sql_str)
        subgraph = cur.fetchall()
    else:
        # create uid table
        temp_sql_str = '''CREATE TABLE OID
                          (id INTEGER PRIMARY KEY AUTOINCREMENT,
                           oid INT NOT NULL);'''
        cur.execute(temp_sql_str)

        # insert data into uid table
        temp_sql_str = "INSERT INTO OID (oid) VALUES (?)"
        oid_tuple_array = [(ele,) for ele in oid_array]
        cur.executemany(temp_sql_str, oid_tuple_array)

        # create index for column oid
        temp_sql_str = "CREATE UNIQUE INDEX oid_oid on OID (oid);"
        cur.execute(temp_sql_str)

        sql_str += ''', UID, OID
                      WHERE EDGE.{} = UID.uid
                      AND EDGE.{} = OID.oid;'''.format(edgelist[0][0], edgelist[0][1])
        cur.execute(sql_str)
        subgraph = cur.fetchall()

    # construct return value
    sub_edgelist = [edgelist[0], edgelist[1]]
    sub_edgelist.append(tuple(subgraph))

    # close db connection
    con.close()

    return sub_edgelist


def _construct_sql_value_placeholder(val_amount):
    if val_amount < 1:
        return None
    else:
        value_placeholder = "(?"
        value_placeholder += ",?" * (val_amount - 1)
        value_placeholder += ")"
        return value_placeholder


if __name__ == '__main__':
    tl = loadTensor('example', path='../inputData', col_types=[int, int])

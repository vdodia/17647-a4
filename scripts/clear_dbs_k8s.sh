#!/usr/bin/env bash
# Clear Aurora books + customers tables and Mongo books collection (EKS / bookstore-ns).
# Run from repo root with kubectl configured. Respects no credentials in git.
set -euo pipefail
NS="${K8S_NAMESPACE:-bookstore-ns}"
export PATH="${HOME}/.local/bin:${PATH}"

echo ">>> clearing books_db (Aurora)"
kubectl exec -n "$NS" deploy/book-command-service -c book-command-service -- python3 -c "
import mysql.connector, os
c = mysql.connector.connect(
  host=os.environ['DATABASE_HOST'], port=3306,
  user=os.environ['MYSQL_USER'], password=os.environ['MYSQL_PASSWORD'],
  database='books_db')
cur = c.cursor()
cur.execute('DELETE FROM books')
c.commit()
cur.execute('SELECT COUNT(*) FROM books')
print('books count', cur.fetchone()[0])
c.close()
"

echo ">>> clearing customers_db (Aurora)"
kubectl exec -n "$NS" deploy/customer-service -c customer-service -- python3 -c "
import mysql.connector, os
c = mysql.connector.connect(
  host=os.environ['DATABASE_HOST'], port=3306,
  user=os.environ['MYSQL_USER'], password=os.environ['MYSQL_PASSWORD'],
  database='customers_db')
cur = c.cursor()
cur.execute('SHOW TABLES LIKE \"customers\"')
if not cur.fetchone():
  print('no customers table yet (run customer-service after init fix / restart)')
  c.close()
  raise SystemExit(0)
cur.execute('DELETE FROM customers')
c.commit()
try:
  cur.execute('ALTER TABLE customers AUTO_INCREMENT = 1')
  c.commit()
except Exception as e:
  print('auto_increment:', e)
cur.execute('SELECT COUNT(*) FROM customers')
print('customers count', cur.fetchone()[0])
c.close()
" || true

echo ">>> clearing Mongo collection"
kubectl exec -n "$NS" deploy/book-query-service -c book-query-service -- python3 -c "
import os
from pymongo import MongoClient
uri = os.environ['MONGO_URI']
dbn = os.environ.get('MONGO_DATABASE','BooksDB')
coln = os.environ.get('MONGO_COLLECTION','books_vdodia')
cl = MongoClient(uri, serverSelectionTimeoutMS=20000)
n = cl[dbn][coln].delete_many({})
print('Mongo deleted', n.deleted_count)
"

echo ">>> done"

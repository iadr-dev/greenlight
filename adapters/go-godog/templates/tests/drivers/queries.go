package drivers

import (
	"strings"
	"sync/atomic"
)

// QueryCounter counts the database statements an action runs, so that an N+1 problem is a failing scenario. Create one
// when the project's System is built, call Record from the application's data access (a database/sql driver wrapper
// such as sqlhooks or go-sqlmock's hooks, a GORM or sqlx callback, or the repository itself), and return Count from
// System.QueriesExecuted.
type QueryCounter struct{ count atomic.Int64 }

// ignored are not counted: transaction control says nothing about the data read.
var ignored = []string{"SAVEPOINT", "RELEASE SAVEPOINT", "ROLLBACK TO SAVEPOINT", "BEGIN", "COMMIT", "ROLLBACK"}

// Record counts one statement.
func (q *QueryCounter) Record(statement string) {
	text := strings.ToUpper(strings.TrimSpace(statement))
	for _, prefix := range ignored {
		if strings.HasPrefix(text, prefix) {
			return
		}
	}
	q.count.Add(1)
}

// Count is the number of statements recorded so far.
func (q *QueryCounter) Count() int { return int(q.count.Load()) }

package greenlight.drivers;

import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;

/**
 * Counting the database statements an action runs, so that an N+1 problem is a failing scenario.
 *
 * <p>{@link #wrap} puts a counting proxy around a {@link DataSource}; GreenlightTestConfig does this for every
 * DataSource bean of the application, so nothing else is needed for plain JDBC, JPA and Spring Data. Savepoints and
 * transaction control are not counted: they say nothing about the data read.
 */
public final class QueryCounter {
    private static final QueryCounter SHARED = new QueryCounter();
    private static final List<String> IGNORED = List.of("SAVEPOINT", "RELEASE SAVEPOINT", "ROLLBACK TO SAVEPOINT",
            "BEGIN", "COMMIT", "ROLLBACK", "SET ");
    private static final Set<String> EXECUTING = Set.of("execute", "executeQuery", "executeUpdate", "executeLargeUpdate",
            "executeBatch", "executeLargeBatch");

    private final AtomicInteger count = new AtomicInteger();
    private volatile boolean attached;

    public static QueryCounter shared() {
        return SHARED;
    }

    public int count() {
        return count.get();
    }

    /** True once a data source has been wrapped; without one there is nothing to count. */
    public boolean attached() {
        return attached;
    }

    public void record(String statement) {
        String head = statement == null ? "" : statement.stripLeading().toUpperCase(Locale.ROOT);
        if (IGNORED.stream().noneMatch(head::startsWith)) {
            count.incrementAndGet();
        }
    }

    public DataSource wrap(DataSource target) {
        attached = true;
        return proxy(DataSource.class, (self, method, args) -> {
            Object result = invoke(method, target, args);
            return "getConnection".equals(method.getName()) && result instanceof Connection connection ? wrap(connection) : result;
        });
    }

    private Connection wrap(Connection target) {
        return proxy(Connection.class, (self, method, args) -> {
            Object result = invoke(method, target, args);
            if ("prepareStatement".equals(method.getName()) && result instanceof PreparedStatement statement) {
                return counting(PreparedStatement.class, statement, (String) args[0]);
            }
            if ("createStatement".equals(method.getName()) && result instanceof Statement statement) {
                return counting(Statement.class, statement, null);
            }
            return result;
        });
    }

    private <T extends Statement> T counting(Class<T> type, T target, String bound) {
        return proxy(type, (self, method, args) -> {
            if (EXECUTING.contains(method.getName())) {
                record(args != null && args.length > 0 && args[0] instanceof String sql ? sql : bound);
            }
            return invoke(method, target, args);
        });
    }

    private static <T> T proxy(Class<T> type, InvocationHandler handler) {
        return type.cast(Proxy.newProxyInstance(type.getClassLoader(), new Class<?>[] {type}, handler));
    }

    private static Object invoke(Method method, Object target, Object[] args) throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException failure) {
            throw failure.getCause();
        }
    }
}

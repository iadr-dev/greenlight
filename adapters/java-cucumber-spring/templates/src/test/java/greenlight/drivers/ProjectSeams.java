package greenlight.drivers;

/**
 * The project's seams. Override the methods of {@link Seams} that the system has, one at a time, from system.md, for
 * example:
 *
 * <pre>
 *   &#64;Override
 *   public List&lt;Map&lt;String, Object&gt;&gt; records(String entity) {
 *       return jdbc().queryForList("select * from " + table(entity));
 *   }
 * </pre>
 *
 * <p>Seams that are not overridden keep failing as an expected failure, which is what the red phase wants.
 */
public class ProjectSeams extends Seams {
    public ProjectSeams(World world) {
        super(world);
    }
}

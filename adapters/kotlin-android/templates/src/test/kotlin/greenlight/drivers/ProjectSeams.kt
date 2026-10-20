package greenlight.drivers

/**
 * The project's seams. Override the methods of [Seams] that the code has, one at a time, from system.md, for example:
 *
 * ```
 * override fun records(entity: String): List<Map<String, Any?>> = database.dao(entity).all()
 * ```
 *
 * Seams that are not overridden keep failing as an expected failure, which is what the red phase wants.
 */
class ProjectSeams(world: World) : Seams(world)

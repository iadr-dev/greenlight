# Adapter guide: java-cucumber-spring

For Spring Boot services tested with Cucumber-JVM on the JUnit Platform, through `MockMvc`. It is the first-class form of
the `generic-junit` contract for this stack: the same steps, drivers and red-phase rules as the other adapters, with the
run command, the report and the classification built in. Tested with Spring Boot 4.1, Cucumber-JVM 8.0, JUnit 6 and
Maven 3.9 on JDK 21 (CI) and 25; Gradle works with the same sources (see below).
`bdd adapter apply java-cucumber-spring` copies `templates/` into the project and registers the adapter in
`.bdd/config.toml`. Nothing is overwritten.

## What you get

| Path | What it is | Who edits it |
|---|---|---|
| `src/test/resources/features/` | the `.feature` files (one sample, `sample.feature`, to delete after the first real feature) | qa-designer |
| `src/test/java/greenlight/steps/CoreSteps.java` | every core instruction of the `base`, `api` and `data` profiles bound to the drivers | nobody: add project steps in their own class |
| `src/test/java/greenlight/steps/{Hooks,ParameterTypes}.java` | per-scenario set-up; one step method takes a table or a doc string | nobody |
| `src/test/java/greenlight/drivers/ProjectSeams.java` | the seams into the system under test: seed, sign in, read records, jobs, events | step-engineer, from `system.md` |
| `src/test/java/greenlight/drivers/Operations.java` | logical name → API route, logical error → status or text | step-engineer, from `system.md` |
| `src/test/java/greenlight/drivers/` (the rest) | clock, stubs, comparison, the API driver, the query counter, the network guard | nobody |
| `RunCucumberTest.java`, `GreenlightSpring.java`, `GreenlightTestConfig.java`, `junit-platform.properties` | which features run, how the Spring context starts, what the tests add to it | nobody (bound) |
| `SampleApplication.java`, `SampleSeams.java` | a stand-in application and in-memory seams for the sample feature | delete with the sample |

## Set up

1. Add the test dependencies to `pom.xml` (the Cucumber BOM keeps the versions together):

   ```xml
   <dependencyManagement><dependencies>
     <dependency><groupId>io.cucumber</groupId><artifactId>cucumber-bom</artifactId>
       <version>8.0.4</version><type>pom</type><scope>import</scope></dependency>
   </dependencies></dependencyManagement>
   <dependencies>
     <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-test</artifactId><scope>test</scope></dependency>
     <dependency><groupId>io.cucumber</groupId><artifactId>cucumber-java</artifactId><scope>test</scope></dependency>
     <dependency><groupId>io.cucumber</groupId><artifactId>cucumber-spring</artifactId><scope>test</scope></dependency>
     <dependency><groupId>io.cucumber</groupId><artifactId>cucumber-junit-platform-engine</artifactId><scope>test</scope></dependency>
     <dependency><groupId>org.junit.platform</groupId><artifactId>junit-platform-suite</artifactId><scope>test</scope></dependency>
   </dependencies>
   ```

   The api profile needs a servlet web application on the classpath (`spring-boot-starter-webmvc`, or
   `spring-boot-starter-web` on older Boot). Install nothing else; the agents are not allowed to change the build.
2. In `GreenlightSpring.java`, replace `SampleApplication.class` with your `@SpringBootApplication` class. Keep
   `GreenlightTestConfig.class`.
3. Run `bdd init --smoke` (or `mvn test -Dtest=RunCucumberTest -Dcucumber.filter.tags=@FEAT-000`): the sample is green.

## The red phase

A scenario must fail for the right reason before any production code exists:

- A seam that is not implemented raises `ExpectedMissing` (the message contains `BDD_EXPECTED_MISSING`): that is an
  *expected* failure. Leave the default in `ProjectSeams` until the system has the seam.
- An API operation answered with 404, 405 or 501 fails the step with `status 404`: also expected.
- A logical name with no entry in `Operations.java` raises `NotMapped`: that is a defect of the *test*. Fix the map, do
  not touch the feature.
- An undefined or ambiguous step, a Spring context that cannot start, a missing class and a compile error are defects
  too. Anything the patterns in `adapter.toml` do not recognise is `unknown` and blocks the gate.

## Filling in the seams

Override the methods of `Seams` in `ProjectSeams`, one at a time, from the system map. Use the most realistic seam: the
API first, then a domain service bean (`world.context.getBean(...)`), then a repository, then the raw `JdbcTemplate`.

- **Clock.** `GreenlightTestConfig` defines a `@Primary` `MutableClock` (a `java.time.Clock`). Code that gets its time
  from an injected `Clock` follows `Given the current time is ...` and `... passes`; code that calls `Instant.now()`
  does not, and `system.md` should say so.
- **Dependencies.** Route outbound calls through a gateway interface whose test implementation calls
  `world.stubs.call(dependency, operation, request)`, or point an HTTP stub library at `world.stubs.respond`. A call the
  scenario did not stub fails the scenario. `NetworkGuard` also refuses JDK `HttpClient` and `HttpURLConnection` calls to
  hosts other than this machine; a library that opens raw sockets itself is not covered (the JVM has no process-wide
  hook for that any more), so run the tests without network access in CI.
- **Queries.** `GreenlightTestConfig` wraps every `DataSource` bean in a counting proxy, so `... ran at most N queries`
  works for plain JDBC, JPA and Spring Data with no seam of your own. Seed three or more records so a query per record
  shows. A scenario that does not count never needs it.
- **Authentication.** Return the headers that prove the sign-in from `authenticate`.
- **Fields the scenario left out.** `complete(operation, fields)` fills in an id or token the request needs.
- **Do not edit the core drivers** (`World`, `ApiDriver`, `Compare`, `Stubs`, `QueryCounter`, `Json`, ...) or `CoreSteps`.
  Project differences go in `ProjectSeams`, `Operations` and your own step classes.

## Writing steps and drivers

- Features contain no paths, class names or SQL; everything concrete lives in `Operations.java` and `ProjectSeams.java`.
- A `Then` step must assert (`bdd scan` reports S2 otherwise); put the comparison in `Compare`.
- No `Thread.sleep`: wait for the condition (`bdd scan` reports E3).
- Stub only the dependencies listed under *Dependencies* in `system.md` (`bdd scan` reports S4 for a `@MockBean`,
  `@MockitoBean`, `@SpyBean` or `Mockito.mock(...)` of anything else).
- Project steps go in their own class under `greenlight.steps`; they must call the same drivers. A step method may take
  a `Payload` (a table or a doc string, whichever the step has) or a `DataTable`.

## Running

```sh
mvn -B test -Dtest=RunCucumberTest -Dcucumber.filter.tags=@FEAT-007            # one feature (tags are Cucumber tags)
mvn -B test -Dtest=RunCucumberTest -Dcucumber.filter.name='^Order of 999$'     # one scenario
mvn -B test -Dtest=RunCucumberTest -Dcucumber.execution.order=random -Dcucumber.execution.order.random.seed=42   # random, repeatable
```

`bdd run FEAT-007` does all of this and records the result (Cucumber's JUnit report, one file); always use it for gates.
On Windows `mvn` is a `.cmd` file, so `bdd run` refuses an argument with characters that `cmd.exe` would read as syntax
(`" & | < > ^ % !`), for example a scenario name containing `&` in `--isolated` mode; the Maven wrapper behaves the same.

## Gradle

The same sources run under Gradle with the JUnit Platform: add the dependencies as `testImplementation`, `useJUnitPlatform()`
in the `test` task, forward `-Pcucumber.*` properties to the test JVM as system properties, and change `by_tag` and the
other `[adapters.run]` words in `.bdd/config.toml` to `./gradlew test --tests greenlight.RunCucumberTest ...`. The
`kotlin-android` adapter ships a Gradle script that does the forwarding; copy it.

## Quality checks (optional)

Name your own tools in `[adapters.quality.NAME]` tables; none is forced. Suggestions that need no plugin of ours:

```toml
[adapters.quality.compile-warnings]      # deprecations and lint warnings are errors; add <compilerArgs> to maven-compiler-plugin
command = 'mvn -B -ntp -q compile -Dmaven.compiler.showDeprecation=true -Dmaven.compiler.failOnWarning=true'

[adapters.quality.format]                # needs the spotless-maven-plugin in the pom
command = 'mvn -B -ntp -q spotless:check'
```

Checkstyle or SpotBugs fit the same way. `.bdd/standards.md` holds the Java and Spring versions, the style and the
deprecation policy these checks enforce.

## What this adapter does not do

- It does not bind `ui`, `cli` or `lib` instructions: UI belongs to `ts-playwright-bdd`, and a library without HTTP is
  better served by the `generic-junit` contract with plain JUnit.
- The `pom.xml` is the project's, so it is not bound by default. A build setting such as `<skipTests>` makes the
  scenarios `not-run`, which blocks the gates rather than faking a pass, but a build plugin could still write a report.
  Add `pom.xml` to `support` in `.bdd/config.toml` once the dependencies are final, and review changes to it.
- Production code runs inside the test JVM and could in principle detect the run; the auditor reads the diff and the
  optional mutation check (`bdd mutate`) adds a second line (PIT fits as the project's wrapper command).

## Known pitfalls

- Two step methods with the same pattern are a duplicate-definition error: use a `Payload` parameter, never one method
  per table or doc string.
- `@SpringBootTest` finds the application class only by package: that is why `GreenlightSpring` names the classes
  explicitly.
- An application that defines its own `Clock` bean works, because the test clock is `@Primary`; one that defines a bean
  named `greenlightClock` collides.
- The Spring context is shared by all scenarios. State that lives in beans (caches, in-memory stores) must be reset in
  `ProjectSeams.reset()`.

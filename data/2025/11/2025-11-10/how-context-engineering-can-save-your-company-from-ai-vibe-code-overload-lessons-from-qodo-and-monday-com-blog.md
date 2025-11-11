### How Context Engineering is Revolutionizing Code Review at monday.com

As companies scale, so do their challenges. For monday.com, a leading cloud project tracking software, the rapid growth of its engineering team—now exceeding 500 developers—brought about a significant hurdle: managing an overwhelming number of pull requests. With product lines multiplying and microservices proliferating, the team needed a solution to ensure quality without drowning in the tedium of manual reviews.

#### The Emergence of Qodo

Enter Qodo, an innovative Israeli startup specializing in developer agents. Initially tested as a lightweight tool, Qodo has since become a cornerstone of monday.com’s software delivery infrastructure. Guy Regev, VP of R&D at monday.com, noted that Qodo feels like an additional team member, one that learns the intricacies of their workflow. This integration has proven invaluable, preventing over 800 issues per month from reaching production—some of which could have resulted in serious security vulnerabilities.

#### What Sets Qodo Apart

Unlike conventional code generation tools, Qodo focuses on reviewing existing code. Its unique approach, termed 'context engineering,' allows it to analyze not just the code changes in a pull request, but also the underlying reasons, business logic, and adherence to internal best practices. Regev emphasized that Qodo’s comments are not generic; they reflect the specific values and standards of monday.com. This context-aware feedback is crucial for maintaining high-quality code as the team expands.

#### The Mechanics of Context Engineering

Qodo’s context engineering involves a comprehensive analysis of various inputs, including prior discussions, documentation, and even relevant files from the repository. By learning from previous pull requests and team interactions, Qodo can catch subtle bugs that human reviewers might overlook. For instance, it flagged a line in a recent pull request that exposed a staging environment variable—an oversight that could have led to significant issues in production.

#### Seamless Integration into Development Workflows

Today, Qodo is deeply embedded in monday.com’s development workflow. It analyzes pull requests and provides context-aware recommendations, allowing developers to remain in control of the final decisions. This human-in-the-loop model has facilitated smoother adoption among the team. The integration with GitHub is straightforward, functioning as a GitHub action that creates a pull request with necessary tests, eliminating the need for a steep learning curve.

#### Significant Improvements and Future Prospects

The results speak for themselves. Since implementing Qodo, monday.com has reported substantial time savings—approximately an hour saved per pull request. Given the volume of pull requests processed monthly, this translates to thousands of developer hours saved annually. The insights provided by Qodo are not merely cosmetic; they address critical issues related to business logic and security.

Regev’s team is so impressed with Qodo’s impact that they are exploring deeper integrations with their developer-focused product line, Monday Dev. The vision is to create a seamless workflow where business context flows directly into the code review process, ensuring that the code not only functions but also addresses the right problems.

As we look ahead, Qodo is poised to become a vital player in the software development landscape. With its freemium model and partnerships with major companies like NVIDIA and Intuit, the potential for growth is immense. As AI continues to evolve, tools like Qodo demonstrate how the right context can transform software development, making it more efficient and effective for teams everywhere.

Source: https://venturebeat.com/ai/how-context-engineering-can-save-your-company-from-ai-vibe-code-overload

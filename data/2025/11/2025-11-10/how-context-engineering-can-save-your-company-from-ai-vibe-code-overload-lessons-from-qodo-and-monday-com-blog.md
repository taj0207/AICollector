### How Context Engineering Transforms Code Review at monday.com

As companies grow, so do their challenges. For monday.com, a cloud project tracking software, scaling to over 500 developers brought about an overwhelming surge in code complexity. With product lines multiplying and microservices proliferating, the engineering team faced a daunting task: how to manage thousands of pull requests each month without compromising quality or overwhelming developers.

#### The Challenge of Scaling

In the fast-paced world of software development, maintaining code quality is paramount. As monday.com expanded, the volume of code flowing through its repositories increased dramatically. Developers were inundated with pull requests, making it difficult for human reviewers to keep pace. The risk of allowing bugs or security vulnerabilities to slip through the cracks became a pressing concern.

#### Enter Qodo: A Game-Changer

To tackle this issue, Guy Regev, VP of R&D at monday.com, turned to Qodo, an Israeli startup specializing in AI-driven developer agents. What started as a simple test quickly evolved into a vital component of monday.com’s software delivery infrastructure. Qodo’s unique approach, termed 'context engineering,' focuses on understanding not just the code changes in a pull request but also the underlying business logic and team-specific standards.

Regev noted that Qodo feels less like a tool and more like an additional team member, capable of learning how the team operates. This context-aware capability has proven transformative, preventing over 800 issues from reaching production each month.

#### The Power of Context Engineering

So, what exactly is context engineering? Qodo’s system analyzes a wide array of inputs when reviewing code, including prior discussions, documentation, and even test results. This holistic approach allows Qodo to catch not only obvious bugs but also subtle issues that human reviewers might miss. For instance, in one notable case, Qodo flagged a line of code that inadvertently exposed a staging environment variable—an oversight that could have led to significant security risks had it been merged.

#### Integration into Development Workflow

Qodo’s integration into monday.com’s development workflow has been seamless. By embedding directly into GitHub, it provides context-aware suggestions during the review process while allowing developers to maintain control over final decisions. This human-in-the-loop model has been crucial for its adoption, enabling developers to learn from the feedback and improve their coding practices.

#### Measurable Results

The impact of Qodo has been significant. Developers have reported saving an average of one hour per pull request, translating to thousands of developer hours saved annually. The suggestions provided by Qodo are not generic; they reflect monday.com’s specific conventions, making it more likely that developers will act on them.

#### Looking Ahead

The success of Qodo has sparked plans for deeper integrations between Qodo and monday.com’s developer-focused product line. The vision is to create a workflow where business context flows directly into the code review process, enabling reviewers to assess not just code functionality but also its alignment with business objectives.

As the landscape of software development continues to evolve, tools like Qodo are leading the charge in demonstrating how context can transform coding practices. With AI becoming increasingly embedded in development workflows, the future is bright for teams that harness the power of context engineering.

Source: https://venturebeat.com/ai/how-context-engineering-can-save-your-company-from-ai-vibe-code-overload

# Java 编码规范

> 适用条件: manifest.tech.language == "java"
> 状态: ⚠️ 待启用（当前默认语言为 python，本规则不会被加载）

## 项目结构
- 使用 Maven 或 Gradle 构建
- 包名全小写（com.example.app）
- 主类放在 `src/main/java/` 下

## 代码风格
- 类名 PascalCase，方法名 camelCase
- 常量 UPPER_SNAKE_CASE
- 每个 public 方法必须有 Javadoc

## Spring Boot 特定（如适用）
- Controller 用 `@RestController`
- 配置从 `application.properties` 或环境变量读取
- 端口: `server.port=${PORT:8080}`

## 安全
- 不硬编码密钥
- SQL 用 PreparedStatement，防注入
- 禁止 `Runtime.exec()` 执行外部命令

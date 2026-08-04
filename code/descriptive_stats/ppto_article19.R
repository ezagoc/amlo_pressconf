library(tidyverse)
source("../../project_paths.R")

df <- readxl::read_xlsx(media_path('data', '01-social_communication', '01-intermediate', 'ppto_article19.xlsx'))

df1 <- df |> select(year, value = exerted) |> mutate(type = 'Approved')

df2 <- df |> select(year, value = approved) |> mutate(type = 'Exerted')

df <- rbind(df1, df2)

ggplot(df, aes(x = year, y = value, color = type)) +
  geom_line(size = 1) +                   # Line thickness for better visibility
  geom_point(size = 2) +                    # Optional: add points to highlight data points
  scale_color_manual(values = c("#2E86C1", "#E74C3C")) +  # Custom colors for lines
  labs(x = "Year",
       y = "Total Approved and Exerted Spending",
       color = "Spending (millions of pesos)") + 
  scale_x_continuous(breaks = 2012:2023) + # Label for the legend
  geom_vline(xintercept = 2019, linetype = "dashed", color = "gray", size = 1) +
  theme_minimal(base_size = 15) +           # Clean theme with adjusted font size
  theme(
    plot.title = element_text(hjust = 0.5, face = "bold"),  # Center title
    plot.subtitle = element_text(hjust = 0.5),
    legend.position = "top"                 # Position legend at the top
  )

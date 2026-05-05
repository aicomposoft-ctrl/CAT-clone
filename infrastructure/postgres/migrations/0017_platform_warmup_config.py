"""
Alembic migration: 0017_platform_warmup_config

Корректирует yandex_warmup в platform_config по результатам тестирования.

Проблема (2026-04-20):
  В ревизии rev 3 yandex_warmup=true был добавлен вручную для всех 4 платформ.
  Тест rev 4 показал регрессию по Ozon: Google warm-up УХУДШАЕТ прохождение
  Akamai Bot Manager на Ozon. Без warm-up Ozon L2 работал (L2 2090 руб).
  Причина: patchright → google.com → ozon.ru выглядит как headless переход,
  а не органический трафик; Akamai детектирует паттерн.

Изменения:
  Лента      → platform_config |= {"yandex_warmup": true}
               Qrator требует органического referer — оставляем.
  Самокат    → platform_config |= {"yandex_warmup": true}
               Аналогично Qrator — оставляем.
  Wildberries → platform_config |= {"yandex_warmup": true}
               wbaas блокирует в любом случае, но warm-up не вредит.
  Ozon       → platform_config - 'yandex_warmup'
               УБИРАЕМ: без warm-up работало (patchright L2 успешен),
               с warm-up — challenge_page (Akamai блокирует).
"""

import json
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Лента, Самокат, WB — добавить/обновить yandex_warmup=true
    op.execute(
        """
        UPDATE platforms
           SET platform_config = COALESCE(platform_config, '{}')::jsonb
                                 || '{"yandex_warmup": true}'::jsonb
         WHERE name IN ('Lenta', 'Самокат', 'Wildberries')
        """
    )

    # Ozon — УБРАТЬ yandex_warmup (warm-up ломает Akamai Bot Manager)
    op.execute(
        """
        UPDATE platforms
           SET platform_config = CASE
               WHEN platform_config IS NULL THEN NULL
               ELSE platform_config - 'yandex_warmup'
           END
         WHERE name = 'Ozon'
        """
    )


def downgrade() -> None:
    # Откатить: убрать yandex_warmup у Лента/Самокат/WB, вернуть Ozon
    op.execute(
        """
        UPDATE platforms
           SET platform_config = CASE
               WHEN platform_config IS NULL THEN NULL
               ELSE platform_config - 'yandex_warmup'
           END
         WHERE name IN ('Lenta', 'Самокат', 'Wildberries')
        """
    )
    op.execute(
        """
        UPDATE platforms
           SET platform_config = COALESCE(platform_config, '{}')::jsonb
                                 || '{"yandex_warmup": true}'::jsonb
         WHERE name = 'Ozon'
        """
    )

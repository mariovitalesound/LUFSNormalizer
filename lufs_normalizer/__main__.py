"""Allow running as: python -m lufs_normalizer"""

import sys
import multiprocessing
multiprocessing.freeze_support()

if len(sys.argv) > 1:
    # CLI mode
    from .cli import main
    main()
else:
    # GUI mode
    from .gui.app import main
    main()

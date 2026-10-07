from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = r"static\pwa"

def create_icon(size):
    image = Image.new("RGB", (size, size), "#0f172a")
    draw = ImageDraw.Draw(image)

    # Rounded background
    radius = int(size * 0.20)
    draw.rounded_rectangle(
        [0, 0, size - 1, size - 1],
        radius=radius,
        fill="#0f172a"
    )

    # Package box
    left = int(size * 0.22)
    top = int(size * 0.30)
    right = int(size * 0.78)
    bottom = int(size * 0.72)

    # Main box
    draw.polygon(
        [
            (left, top),
            (right, top),
            (right, bottom),
            (left, bottom)
        ],
        fill="#f59e0b"
    )

    # Top flap
    draw.polygon(
        [
            (left, top),
            (size // 2, int(size * 0.20)),
            (right, top),
            (size // 2, int(size * 0.38))
        ],
        fill="#fbbf24"
    )

    # Left side
    draw.polygon(
        [
            (left, top),
            (size // 2, int(size * 0.38)),
            (size // 2, bottom),
            (left, bottom)
        ],
        fill="#d97706"
    )

    # Center tape
    tape_width = max(8, int(size * 0.09))

    draw.rectangle(
        [
            size // 2 - tape_width // 2,
            int(size * 0.21),
            size // 2 + tape_width // 2,
            bottom
        ],
        fill="#fff7ed"
    )

    # Small highlight
    draw.line(
        [
            (int(size * 0.29), int(size * 0.39)),
            (int(size * 0.29), int(size * 0.62))
        ],
        fill="#fbbf24",
        width=max(2, int(size * 0.015))
    )

    path = f"{OUTPUT_DIR}\\icon-{size}.png"
    image.save(path, "PNG", optimize=True)

    print(f"Created: {path}")


create_icon(192)
create_icon(512)

print()
print("PWA icons created successfully.")
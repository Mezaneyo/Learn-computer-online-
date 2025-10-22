import java.util.Scanner;

public class QuadraticEquation {
    public static void main(String[] args) {
        double a, b, c, discriminant, root1, root2, realPart, imagPart;
        Scanner input = new Scanner(System.in);

        System.out.print("Enter value of a: ");
        a = input.nextDouble();
        System.out.print("Enter value of b: ");
        b = input.nextDouble();
        System.out.print("Enter value of c: ");
        c = input.nextDouble();

        discriminant = b * b - 4 * a * c;

        if (discriminant > 0) {
            root1 = (-b + Math.sqrt(discriminant)) / (2 * a);
            root2 = (-b - Math.sqrt(discriminant)) / (2 * a);
            System.out.println("Roots are real and distinct.");
            System.out.println("Root 1 = " + root1);
            System.out.println("Root 2 = " + root2);
        } 
        else if (discriminant == 0) {
            root1 = -b / (2 * a);
            System.out.println("Roots are real and equal.");
            System.out.println("Root 1 = Root 2 = " + root1);
        } 
        else {
            realPart = -b / (2 * a);
            imagPart = Math.sqrt(-discriminant) / (2 * a);
            System.out.println("Roots are complex and different.");
            System.out.println("Root 1 = " + realPart + " + " + imagPart + "i");
            System.out.println("Root 2 = " + realPart + " - " + imagPart + "i");
        }

        input.close();
    }
}
